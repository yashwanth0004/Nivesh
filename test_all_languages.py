import traceback
from models.translate2 import load_translation_models, translate_english_to_indic, translate_indic_to_english, LANGUAGE_MAP

def test_translation(sentence: str):
    try:
        engines = load_translation_models()
    except Exception as e:
        print(f"Failed to load models: {e}")
        return
    for shortcut, script_tag in LANGUAGE_MAP.items():
        if shortcut == "en":
            continue
        print(f"\n=== Testing language '{shortcut}' ({script_tag}) ===")
        # English to Indic
        try:
            eng_to_indic = translate_english_to_indic(engines, sentence, shortcut)
            print(f"EN -> {shortcut}: {eng_to_indic}")
        except Exception as e:
            print(f"Error EN->{shortcut}: {e}\n{traceback.format_exc()}")
        # Indic back to English (using the same sentence but in target language)
        # For testing, we use the result of EN->Indic as source if it succeeded
        if 'eng_to_indic' in locals() and isinstance(eng_to_indic, str) and not eng_to_indic.startswith('Error'):
            try:
                back_to_eng = translate_indic_to_english(engines, eng_to_indic, shortcut)
                print(f"{shortcut} -> EN: {back_to_eng}")
            except Exception as e:
                print(f"Error {shortcut}->EN: {e}\n{traceback.format_exc()}")
        else:
            print("Skipping Indic->EN due to previous error.")

if __name__ == "__main__":
    test_sentence = "hi my name is yashwanth and i want to invest in stocks and gain some profits , will i get profits"
    test_translation(test_sentence)
