import os
import json
from pathlib import Path
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer
from download_models import ensure_translation_model

# ---------------------------------------------------------------------------
# Exhaustive mapping of ALL 22 scheduled languages + English
# Uses the CORRECT FLORES-200 tags that match the IndicTrans2 ONNX model's
# special tokens. Key corrections:
#   - Nepali uses "npi_Deva" (NOT "nep_Deva")
#   - Konkani uses "gom_Deva" (NOT "kok_Deva")
# ---------------------------------------------------------------------------
LANGUAGE_MAP = {
    "as":  "asm_Beng",   # Assamese
    "bn":  "ben_Beng",   # Bengali
    "brx": "brx_Deva",   # Bodo
    "doi": "doi_Deva",   # Dogri
    "gu":  "guj_Gujr",   # Gujarati
    "hi":  "hin_Deva",   # Hindi
    "kn":  "kan_Knda",   # Kannada
    "ks":  "kas_Arab",   # Kashmiri
    "kok": "gom_Deva",   # Konkani  (FLORES-200 uses Goan Konkani code)
    "mai": "mai_Deva",   # Maithili
    "ml":  "mal_Mlym",   # Malayalam
    "mni": "mni_Beng",   # Manipuri (Bengali script)
    "mr":  "mar_Deva",   # Marathi
    "ne":  "npi_Deva",   # Nepali   (FLORES-200 uses "npi" not "nep")
    "or":  "ory_Orya",   # Odia (Oriya)
    "pa":  "pan_Guru",   # Punjabi (Gurmukhi)
    "sa":  "san_Deva",   # Sanskrit
    "sat": "sat_Olck",   # Santali (Ol Chiki)
    "sd":  "snd_Arab",   # Sindhi
    "ta":  "tam_Taml",   # Tamil
    "te":  "tel_Telu",   # Telugu
    "ur":  "urd_Arab",   # Urdu
    "en":  "eng_Latn"    # English
}

# The set of all supported FLORES tags (for validation)
SUPPORTED_LANG_TAGS = set(LANGUAGE_MAP.values())

# Maximum input sequence length the ONNX model's positional embeddings support
MAX_SEQ_LEN = 256


def convert_to_native_utf8_font(text, target_lang_tag):
    """
    The IndicTrans2 model outputs all Indic text in Devanagari script internally.
    This function maps Devanagari codepoints to the correct native script for
    non-Devanagari languages (Bengali, Gujarati, Telugu, Tamil, etc.).
    
    Languages that already use Devanagari (Hindi, Marathi, Sanskrit, etc.),
    Arabic script (Urdu, Kashmiri, Sindhi), Latin (English), or Ol Chiki (Santali)
    are returned as-is.
    """
    # Languages whose output is already in the correct script
    NO_CONVERSION = {
        "hin_Deva", "mar_Deva", "san_Deva", "npi_Deva",
        "gom_Deva", "brx_Deva", "doi_Deva", "mai_Deva",
        "urd_Arab", "kas_Arab", "snd_Arab",
        "eng_Latn", "sat_Olck"
    }
    if target_lang_tag in NO_CONVERSION:
        return text

    DEVA_START = 0x0900
    DEVA_END = 0x097F
    
    # Unicode block offsets relative to Devanagari
    OFFSETS = {
        "asm_Beng": 0x0980 - DEVA_START,   # Assamese (uses Bengali script)
        "ben_Beng": 0x0980 - DEVA_START,   # Bengali
        "pan_Guru": 0x0A00 - DEVA_START,   # Punjabi (Gurmukhi)
        "guj_Gujr": 0x0A80 - DEVA_START,   # Gujarati
        "ory_Orya": 0x0B00 - DEVA_START,   # Odia
        "tam_Taml": 0x0B80 - DEVA_START,   # Tamil
        "tel_Telu": 0x0C00 - DEVA_START,   # Telugu
        "kan_Knda": 0x0C80 - DEVA_START,   # Kannada
        "mal_Mlym": 0x0D00 - DEVA_START,   # Malayalam
        "mni_Beng": 0x0980 - DEVA_START    # Manipuri (Bengali script)
    }

    offset = OFFSETS.get(target_lang_tag)
    if offset is None:
        return text

    native_chars = []
    for char in text:
        cp = ord(char)
        if DEVA_START <= cp <= DEVA_END:
            target_cp = cp + offset
            # Skip codepoints that don't exist in Tamil script
            if target_lang_tag == "tam_Taml" and target_cp in {
                0x0B84, 0x0B8B, 0x0B8C, 0x0B91,
                0x0B96, 0x0B97, 0x0B98,
                0x0BA0, 0x0BA1, 0x0BA2
            }:
                continue
            # Skip codepoints that don't exist in Gurmukhi script
            elif target_lang_tag == "pan_Guru" and target_cp in {
                0x0A04, 0x0A0B, 0x0A0C, 0x0A11, 0x0A12,
                0x0A29, 0x0A31, 0x0A34, 0x0A37
            }:
                continue
            native_chars.append(chr(target_cp))
        else:
            native_chars.append(char)

    return "".join(native_chars)


# -------------------------------------------------------------------
# HELPER: Apply repetition penalty to logits
# -------------------------------------------------------------------
def _apply_repetition_penalty(logits, generated_ids, penalty=1.5):
    """
    Penalize tokens that have already been generated to prevent
    repetition loops. This modifies logits in-place.
    
    For each previously generated token:
      - If logit > 0, divide by penalty
      - If logit < 0, multiply by penalty
    """
    if penalty == 1.0 or len(generated_ids) == 0:
        return logits
    
    for token_id in set(generated_ids):
        if token_id < logits.shape[-1]:
            if logits[0, -1, token_id] > 0:
                logits[0, -1, token_id] /= penalty
            else:
                logits[0, -1, token_id] *= penalty
    return logits


# -------------------------------------------------------------------
# HELPER GENERATION CORE (Private Internal Processor)
# -------------------------------------------------------------------
def _execute_onnx_inference(engine, formatted_text, target_lang_tag,
                            max_length=128, repetition_penalty=1.5):
    """
    Handles matrix array calculations across encoder and decoder graphs.
    Includes input truncation (to avoid position embedding overflow)
    and repetition penalty (to avoid output loops).
    """
    encoded = engine['tokenizer_src'].encode(formatted_text)
    input_ids_list = encoded.ids

    # Some bundled tokenizer exports contain token IDs beyond the ONNX
    # encoder's embedding table. Map those rare tokens to the tokenizer's
    # unknown token instead of letting ONNX fail with Gather out-of-bounds.
    src_vocab_size = engine.get('src_vocab_size')
    if src_vocab_size:
        unknown_id = engine.get('src_unk_id', 3)
        input_ids_list = [token_id if 0 <= token_id < src_vocab_size else unknown_id
                          for token_id in input_ids_list]
    
    # --- TRUNCATION: Ensure input doesn't exceed model's max positional embedding ---
    # The ONNX model supports max 256 input positions (+ 2 offset = 258 embeddings)
    if len(input_ids_list) > MAX_SEQ_LEN:
        input_ids_list = input_ids_list[:MAX_SEQ_LEN]
    
    input_ids = np.array([input_ids_list], dtype=np.int64)
    attention_mask = np.ones_like(input_ids, dtype=np.int64)

    enc_inputs = {'input_ids': input_ids, 'attention_mask': attention_mask}
    enc_outputs = engine['encoder'].run(None, enc_inputs)
    
    last_hidden_state = enc_outputs[0]
    if len(last_hidden_state.shape) == 4:
        last_hidden_state = np.squeeze(last_hidden_state, axis=0)

    # The decoder always starts with the EOS token (</s>) as the initial seed.
    eos_token_id = engine['tokenizer_tgt'].token_to_id("</s>")
    decoder_input_ids = np.array([[eos_token_id]], dtype=np.int64)
    decoder_expected_inputs = [x.name for x in engine['decoder'].get_inputs()]
    
    generated_token_ids = []
    
    for _ in range(max_length):
        dec_inputs = {}
        if 'input_ids' in decoder_expected_inputs:
            dec_inputs['input_ids'] = decoder_input_ids
        if 'encoder_hidden_states' in decoder_expected_inputs:
            dec_inputs['encoder_hidden_states'] = last_hidden_state
        if 'encoder_attention_mask' in decoder_expected_inputs:
            dec_inputs['encoder_attention_mask'] = attention_mask
        elif 'attention_mask' in decoder_expected_inputs and 'input_ids' in dec_inputs:
            dec_inputs['attention_mask'] = attention_mask

        dec_outputs = engine['decoder'].run(None, dec_inputs)
        next_token_logits = dec_outputs[0]
        
        # --- REPETITION PENALTY: Prevent output loops ---
        next_token_logits = _apply_repetition_penalty(
            next_token_logits, generated_token_ids, penalty=repetition_penalty
        )
        
        next_token = int(np.argmax(next_token_logits[0, -1, :]))

        decoder_input_ids = np.hstack([decoder_input_ids, [[next_token]]])
        generated_token_ids.append(next_token)
        
        if next_token == eos_token_id:
            break
            
    flat_token_list = decoder_input_ids.flatten().tolist()
    raw_text_output = engine['tokenizer_tgt'].decode(flat_token_list, skip_special_tokens=True)
    
    # Convert Devanagari output to native script for non-Devanagari languages
    return convert_to_native_utf8_font(raw_text_output, target_lang_tag)


# -------------------------------------------------------------------
# FUNCTION 1: Load Translation Models Completely Offline
# -------------------------------------------------------------------
class _IndicTransONNX:
    """Greedy ONNX decoder for the compact Hugging Face IndicTrans2 exports."""

    def __init__(self, folder_path):
        from IndicTransToolkit import IndicProcessor

        self.folder = Path(folder_path)
        self.processor = IndicProcessor(inference=True)
        self.src_tokenizer = Tokenizer.from_file(str(self.folder / "tokenizer_src.json"))
        self.tgt_tokenizer = Tokenizer.from_file(str(self.folder / "tokenizer_tgt.json"))
        metadata = json.loads((self.folder / "tokenizer_meta.json").read_text(encoding="utf-8"))
        generation = json.loads((self.folder / "generation_config.json").read_text(encoding="utf-8"))
        self.src_vocab_size = int(metadata["src_dict_size"])
        self.tgt_vocab_size = int(metadata["tgt_dict_size"])
        self.unk_id = int(metadata.get("unk_id", 3))
        self.start_id = int(generation.get("decoder_start_token_id", 2))
        self.eos_id = int(generation.get("eos_token_id", 2))

        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 2
        self.encoder = ort.InferenceSession(
            str(self.folder / "encoder_model.onnx"),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self.decoder = ort.InferenceSession(
            str(self.folder / "decoder_model.onnx"),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self.decoder_past = ort.InferenceSession(
            str(self.folder / "decoder_with_past_model.onnx"),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self.num_layers = (len(self.decoder.get_outputs()) - 1) // 4

    def translate(self, text, src_lang, tgt_lang, max_new_tokens=128):
        if hasattr(self.processor, "_placeholder_entity_maps"):
            self.processor._placeholder_entity_maps.queue.clear()
        prepared = self.processor.preprocess_batch(
            [text], src_lang=src_lang, tgt_lang=tgt_lang
        )[0]
        encoded = self.src_tokenizer.encode(prepared)
        source_ids = [
            token_id if token_id < self.src_vocab_size else self.unk_id
            for token_id in encoded.ids[:MAX_SEQ_LEN]
        ]
        input_ids = np.array([source_ids], dtype=np.int64)
        attention_mask = np.ones_like(input_ids, dtype=np.int64)
        encoder_state = self.encoder.run(
            ["last_hidden_state"],
            {"input_ids": input_ids, "attention_mask": attention_mask},
        )[0]

        decoder_ids = np.array([[self.start_id]], dtype=np.int64)
        generated_ids = [self.start_id]
        past_outputs = None
        for step in range(max_new_tokens):
            if step == 0:
                outputs = self.decoder.run(None, {
                    "input_ids": decoder_ids,
                    "encoder_hidden_states": encoder_state,
                    "encoder_attention_mask": attention_mask,
                })
            else:
                past_inputs = {}
                for layer in range(self.num_layers):
                    base = layer * 4
                    past_inputs[f"past_key_values.{layer}.decoder.key"] = past_outputs[base]
                    past_inputs[f"past_key_values.{layer}.decoder.value"] = past_outputs[base + 1]
                    past_inputs[f"past_key_values.{layer}.encoder.key"] = past_outputs[base + 2]
                    past_inputs[f"past_key_values.{layer}.encoder.value"] = past_outputs[base + 3]
                outputs = self.decoder_past.run(None, {
                    "input_ids": decoder_ids,
                    "encoder_attention_mask": attention_mask,
                    **past_inputs,
                })

            logits = outputs[0]
            past_outputs = list(outputs[1:])
            next_id = int(np.argmax(logits[0, -1, :]))
            generated_ids.append(next_id)
            if next_id == self.eos_id:
                break
            decoder_ids = np.array([[next_id]], dtype=np.int64)

        safe_ids = [
            token_id if token_id < self.tgt_vocab_size else self.unk_id
            for token_id in generated_ids
        ]
        raw_text = self.tgt_tokenizer.decode(safe_ids, skip_special_tokens=True)
        return self.processor.postprocess_batch([raw_text], lang=tgt_lang)[0]


def load_translation_models(en_to_indic_path=None, indic_to_en_path=None, include_indic_to_en=True):
    """
    Mounts the encoder and decoder inference graphs alongside the source/target tokenizers.
    Automatically resolves model paths relative to the script's directory.
    """
    script_dir = Path(__file__).resolve().parent
    parent_dir = script_dir.parent
    if en_to_indic_path is None:
        en_to_indic_path = parent_dir / "models_trans" / "model_en_to_indic"
    if indic_to_en_path is None:
        indic_to_en_path = parent_dir / "models_trans" / "model_indic_to_en"

    engines = {}

    def setup_engine(folder_path, model_name):
        folder_path = Path(folder_path)
        model_root = folder_path.parent.parent if folder_path.parent.name == "models_trans" else parent_dir
        resolved_folder = ensure_translation_model(model_name, model_root)
        return _IndicTransONNX(resolved_folder)

    print("⏳ Mounting translation execution models into local RAM...")
    engines['en_to_indic'] = setup_engine(en_to_indic_path, "model_en_to_indic")
    engines['indic_to_en'] = setup_engine(indic_to_en_path, "model_indic_to_en") if include_indic_to_en else None

    if not engines['en_to_indic'] and not engines['indic_to_en']:
        raise FileNotFoundError("❌ Crash: The ONNX models could not be verified. Check file placements.")

    print("✨ Translation model(s) are ready.")
    return engines


# -------------------------------------------------------------------
# FUNCTION 2: English to Indic Translation
# -------------------------------------------------------------------
def translate_english_to_indic(engines, text, target_lang_shortcut):
    """
    Translates English text into a target Indian language using its shortcut.
    Example: target_lang_shortcut="te" (Telugu), "hi" (Hindi).
    """
    engine = engines.get('en_to_indic')
    if not engine:
        return "Error: English to Indic models are not loaded in the system."
    tgt_lang = LANGUAGE_MAP.get(target_lang_shortcut.lower())
    if not tgt_lang:
        return f"Error: Language shortcut '{target_lang_shortcut}' is invalid."
    if tgt_lang == "eng_Latn":
        return "Error: Cannot translate English to English. Select an Indic language."
    return engine.translate(text, src_lang="eng_Latn", tgt_lang=tgt_lang)


# -------------------------------------------------------------------
# FUNCTION 3: Indic to English Translation
# -------------------------------------------------------------------
def translate_indic_to_english(engines, text, source_lang_shortcut):
    """
    Translates Indian language text into English using its shortcut.
    Example: source_lang_shortcut="te" (Telugu), "hi" (Hindi).
    """
    engine = engines.get('indic_to_en')
    if not engine:
        return "Error: Indic to English models are not loaded in the system."
    src_lang = LANGUAGE_MAP.get(source_lang_shortcut.lower())
    if not src_lang:
        return f"Error: Language shortcut '{source_lang_shortcut}' is invalid."
    if src_lang == "eng_Latn":
        return "Error: Cannot translate English to English. Select an Indic language."
    return engine.translate(text, src_lang=src_lang, tgt_lang="eng_Latn")


# -------------------------------------------------------------------
# MAIN INTERACTIVE PIPELINE EXECUTION
# -------------------------------------------------------------------
if __name__ == "__main__":
    # 1. Initialization phase outside the loop boundaries
    try:
        translation_system = load_translation_models()
    except Exception as e:
        print(f"CRITICAL ERROR loading models: {e}")
        exit(1)
        
    print("\n==============================================")
    print("    🇮🇳 Local Low-Memory 22-Language Translator     ")
    print("==============================================")
    print("Supported language shortcuts:")
    for code, tag in sorted(LANGUAGE_MAP.items()):
        if code != "en":
            print(f"  {code:>4s} → {tag}")

    # 2. Main workflow routing control block
    while True:
        print("\nSelect Mode:")
        print("1. English ➡️  Indian Language")
        print("2. Indian Language ➡️  English")
        print("3. Exit Program")
        
        mode = input("Enter option (1/2/3): ").strip()
        
        if mode == "3":
            print("Exiting translator loop. Goodbye!")
            break
            
        if mode not in ["1", "2"]:
            print("❌ Invalid entry. Select 1, 2, or 3.")
            continue
            
        shortcut = input("Enter language shortcut (e.g. te, hi, as, bn): ").strip().lower()
        if shortcut not in LANGUAGE_MAP or shortcut == "en":
            print(f"❌ '{shortcut}' is an invalid or unsupported language shortcut choice.")
            continue
            
        user_text = input("Enter the text sentence to translate: ").strip()
        if not user_text:
            print("❌ Input text cannot be left empty.")
            continue

        print("\n🔄 Processing translation locally on CPU...")
        if mode == "1":
            result = translate_english_to_indic(translation_system, user_text, shortcut)
            print(f"👉 Result: {result}")
        else:
            result = translate_indic_to_english(translation_system, user_text, shortcut)
            print(f"👉 Result: {result}")

