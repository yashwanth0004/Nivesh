"""
main_app.py  –  UNIFIED ENTRY POINT
======================================
Connects:
  test.py    → Sherpa-ONNX offline speech recognition (voice input)
  model_7.py → Qwen 3:8B + ChromaDB RAG              (AI brain)
  listen1.py → gTTS + pygame                          (voice output)

Flow after every AI answer:
  ┌──────────────────────────────────────┐
  │  What would you like to do next?     │
  │  1 - Ask another question (Voice)    │
  │  2 - Switch to Text input            │
  │  0 - Exit                            │
  └──────────────────────────────────────┘

TTS pipeline — TWO THREADS, NO GAPS:
  Thread-A: text → gTTS → mp3 bytes  (network, runs while B is playing)
  Thread-B: mp3 bytes → play          (local, plays immediately when ready)

Run:
    python main_app.py
"""

import os
import sys
import io
import re
import time
import queue
import threading
import numpy as np

# ── Windows: force UTF-8 console ─────────────────────────────────────────────
if sys.platform == "win32":
    import msvcrt
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

import sounddevice as sd
import sherpa_onnx
import model_7    # AI brain  (model_7.py)
import listen1    # TTS       (listen1.py)

# ── VAD constants — identical to test.py ─────────────────────────────────────
SAMPLE_RATE      = 16000
BLOCK_SIZE       = 1600      # 100 ms per chunk
VAD_THRESHOLD    = 0.008     # RMS below this = silence
SILENCE_DURATION = 1.0       # seconds of silence → end of utterance

_STOP = object()   # sentinel to stop worker threads


# ─────────────────────────────────────────────────────────────────────────────
# STT text cleanup — exact copy from test.py
# ─────────────────────────────────────────────────────────────────────────────
def _clean_stt_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace(" ", " ").replace("▁", " ")
    text = re.sub(r"([a-zA-Z]+)([^a-zA-Z\s])", r"\1 \2", text)
    text = re.sub(r"([^a-zA-Z\s])([a-zA-Z]+)", r"\1 \2", text)
    return " ".join(text.split())


# ─────────────────────────────────────────────────────────────────────────────
# Non-blocking 'q' key check — identical to test.py
# ─────────────────────────────────────────────────────────────────────────────
def _check_quit_key() -> bool:
    if sys.platform == "win32":
        if msvcrt.kbhit():
            return msvcrt.getch().decode("utf-8", errors="ignore").lower() == "q"
    else:
        import select
        dr, _, _ = select.select([sys.stdin], [], [], 0)
        if dr:
            return sys.stdin.read(1).lower() == "q"
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Load Sherpa-ONNX STT model — same logic as test.py
# ─────────────────────────────────────────────────────────────────────────────
def load_stt_model(language_code: str):
    model_path  = f"./models/{language_code}/model.int8.onnx"
    tokens_path = "./models/tokens1.txt" if language_code == "en" else "./models/tokens.txt"

    if not os.path.exists(model_path):
        print(f"[ERROR] STT model not found: {model_path}")
        return None
    if not os.path.exists(tokens_path):
        print(f"[ERROR] Tokens file not found: {tokens_path}")
        return None

    print(f"\n[STT] Loading [{language_code.upper()}] Sherpa-ONNX engine (~300 MB)...")
    rec = sherpa_onnx.OfflineRecognizer.from_nemo_ctc(
        model=model_path,
        tokens=tokens_path,
        num_threads=4,
        decoding_method="greedy_search",
        debug=False,
    )
    print("[STT] Speech recognition engine ready.")
    return rec


# ─────────────────────────────────────────────────────────────────────────────
# Flush stale mic frames accumulated while AI/TTS was active
# ─────────────────────────────────────────────────────────────────────────────
def _flush_mic(stream, seconds: float = 0.8):
    chunks = int((seconds * SAMPLE_RATE) / BLOCK_SIZE) + 1
    for _ in range(chunks):
        try:
            stream.read(BLOCK_SIZE)
        except Exception:
            break


# ─────────────────────────────────────────────────────────────────────────────
# TWO-THREAD STREAMING TTS PIPELINE
#   sentence_q → [Thread-A: audio generator] → audio_q → [Thread-B: player]
#
# Thread-A fetches the next sentence's audio while Thread-B is still playing
# the current one — seamless, gap-free speech.
# ─────────────────────────────────────────────────────────────────────────────
def _audio_gen_thread(sentence_q: queue.Queue,
                      audio_q:    queue.Queue,
                      lang_code:  str):
    while True:
        item = sentence_q.get()
        if item is _STOP:
            audio_q.put(_STOP)
            sentence_q.task_done()
            break
        mp3 = listen1.generate_audio_bytes(item, lang_code=lang_code)
        audio_q.put(mp3)   # None if generation failed; player will skip
        sentence_q.task_done()


def _audio_play_thread(audio_q: queue.Queue):
    while True:
        item = audio_q.get()
        if item is _STOP:
            audio_q.task_done()
            break
        if item is not None:
            listen1.play_audio_bytes(item)
        audio_q.task_done()


def speak_streaming(spoken_text: str, lang_code: str) -> str:
    """
    Run AI generation + two-thread TTS concurrently.
    Returns the full AI response text when both generation and playback finish.
    """
    sentence_q = queue.Queue()
    audio_q    = queue.Queue(maxsize=3)
    full_parts = []

    gen_t  = threading.Thread(target=_audio_gen_thread,
                               args=(sentence_q, audio_q, lang_code), daemon=True)
    play_t = threading.Thread(target=_audio_play_thread,
                               args=(audio_q,), daemon=True)
    gen_t.start()
    play_t.start()

    try:
        for sentence in model_7.stream_sentences(spoken_text, lang_code=lang_code):
            full_parts.append(sentence)
            sentence_q.put(sentence)
    except Exception as e:
        print(f"\n[Streaming error]: {e}")

    sentence_q.put(_STOP)
    gen_t.join()
    play_t.join()

    return " ".join(full_parts)


# ─────────────────────────────────────────────────────────────────────────────
# POST-RESPONSE MENU
# Shown after every AI answer. Returns: 'voice', 'text', or 'exit'
# ─────────────────────────────────────────────────────────────────────────────
def _ask_next_action(stt_available: bool) -> str:
    """
    Ask the user what to do after the AI has finished answering.
    Returns one of: 'voice', 'text', 'exit'
    """
    print("\n" + "-" * 50)
    print("  What would you like to do next?")
    if stt_available:
        print("  1 - Ask another question  (Voice)")
    print("  2 - Type a question        (Text)")
    print("  0 - Exit")
    print("-" * 50)

    while True:
        try:
            choice = input("  Enter 1, 2, or 0: ").strip()
        except (EOFError, KeyboardInterrupt):
            return "exit"

        if choice == "1" and stt_available:
            return "voice"
        if choice == "1" and not stt_available:
            print("  [Voice Mode unavailable — STT model missing.]")
        elif choice == "2":
            return "text"
        elif choice == "0":
            return "exit"
        else:
            print("  Invalid choice — enter 1, 2, or 0.")


# ─────────────────────────────────────────────────────────────────────────────
# CAPTURE ONE VOICE UTTERANCE
# Listens until silence detected, transcribes, returns text.
# Returns None if quit key pressed.
# ─────────────────────────────────────────────────────────────────────────────
def _capture_voice(recognizer, mic_stream) -> str | None:
    """
    Listen via mic until sustained silence, transcribe with Sherpa-ONNX.
    Returns transcribed text, or None if user presses 'q'.
    """
    audio_buffer  = []
    is_speaking   = False
    silence_start = None

    while True:
        if _check_quit_key():
            return None

        samples, _ = mic_stream.read(BLOCK_SIZE)
        samples    = samples.flatten()
        rms = float(np.sqrt(np.mean(samples ** 2))) if len(samples) > 0 else 0.0

        if rms > VAD_THRESHOLD:
            if not is_speaking:
                is_speaking = True
            audio_buffer.extend(samples.tolist())
            silence_start = None
        else:
            if is_speaking:
                audio_buffer.extend(samples.tolist())
                if silence_start is None:
                    silence_start = time.time()
                if time.time() - silence_start >= SILENCE_DURATION:
                    # Transcribe
                    stt_s = recognizer.create_stream()
                    stt_s.accept_waveform(16000.0, audio_buffer)
                    recognizer.decode_stream(stt_s)
                    return _clean_stt_text(stt_s.result.text)

        time.sleep(0.01)


# ─────────────────────────────────────────────────────────────────────────────
# ONE VOICE INTERACTION
# Listens → transcribes → AI answers → returns next action
# ─────────────────────────────────────────────────────────────────────────────
def voice_interaction(language_code: str, recognizer, stt_available: bool) -> str:
    """
    Performs one full voice interaction cycle.
    Returns the next mode: 'voice', 'text', or 'exit'.
    """
    print("\nListening....")
    time.sleep(1.0)          # 1-second buffer before recording starts

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        blocksize=BLOCK_SIZE,
    ) as mic_stream:

        _flush_mic(mic_stream, seconds=0.5)   # discard pre-open buffer
        print(">>> Speak your question now  (press q + Enter to go back)\n")

        spoken_text = _capture_voice(recognizer, mic_stream)

        if spoken_text is None:
            print("\n[Cancelled — returning to menu]")
            return _ask_next_action(stt_available)

        if not spoken_text.strip():
            print("[Nothing heard — please try again.]")
            return "voice"   # retry immediately

        print(f"\nYou said: {spoken_text}")

        # AI answer + streaming TTS
        speak_streaming(spoken_text, lang_code=language_code)

        # Flush mic after TTS finishes (discard speaker bleed)
        _flush_mic(mic_stream, seconds=0.8)

    return _ask_next_action(stt_available)


# ─────────────────────────────────────────────────────────────────────────────
# ONE TEXT INTERACTION
# User types → AI answers (text only) → returns next action
# ─────────────────────────────────────────────────────────────────────────────
def text_interaction(language_code: str, stt_available: bool) -> str:
    """
    Performs one full text interaction cycle.
    Returns the next mode: 'voice', 'text', or 'exit'.
    """
    lang_name = model_7._get_language_name(language_code)
    print(f"\n[Text Mode | Language: {lang_name}]")
    print("Type your question (or type  exit  to go back to menu):\n")

    try:
        user_input = input("You: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n[Interrupted]")
        return _ask_next_action(stt_available)

    if user_input.lower() in ["exit", "quit", "back", "0"]:
        return _ask_next_action(stt_available)

    if not user_input:
        return "text"

    model_7.chat_with_bot_stream(user_input, lang_code=language_code)
    return _ask_next_action(stt_available)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN — startup + interaction loop
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print("\n" + "=" * 60)
    print("  FINANCIAL EDUCATION AI  —  INVESTOR RESILIENCE ASSISTANT")
    print("  Qwen 3:8B  |  Sherpa-ONNX STT  |  Streaming gTTS")
    print("=" * 60)

    # ── Language selection ────────────────────────────────────────────────────
    print("\nAvailable language codes:")
    print("  en — English    hi — Hindi    te — Telugu")
    print("  ta — Tamil      kn — Kannada  ml — Malayalam\n")

    language_code = input("Enter language code: ").strip().lower() or "en"
    lang_name     = model_7._get_language_name(language_code)
    print(f"Language set to: {lang_name}\n")

    # ── Load ALL models once — stay in RAM for website / long-running use ─────
    print("Loading all models — please wait...\n")

    model_7.initialize()                          # Qwen + embeddings + ChromaDB

    recognizer    = load_stt_model(language_code)
    stt_available = recognizer is not None
    if not stt_available:
        print(f"[WARN] STT model for '{language_code}' not found. Voice Mode disabled.\n")

    print("[TTS] gTTS + pygame pipeline ready.\n")
    print("=" * 60)
    print("  All systems ready!")
    print("=" * 60)

    # ── Choose starting mode ──────────────────────────────────────────────────
    print("\nHow would you like to start?")
    if stt_available:
        print("  1 - Voice Mode  (speak your question)")
    print("  2 - Text Mode   (type your question)")
    print("  0 - Exit")

    while True:
        choice = input("  Enter 1, 2, or 0: ").strip()
        if choice == "1" and stt_available:
            current_mode = "voice"
            break
        elif choice == "1" and not stt_available:
            print("  [Voice Mode unavailable — STT model missing.]")
        elif choice == "2":
            current_mode = "text"
            break
        elif choice == "0":
            print("\nGoodbye!\n")
            return
        else:
            print("  Invalid choice.")

    # ── Main interaction loop ─────────────────────────────────────────────────
    while current_mode != "exit":
        try:
            if current_mode == "voice":
                if stt_available:
                    current_mode = voice_interaction(language_code, recognizer, stt_available)
                else:
                    print("\n[Voice Mode unavailable] Switching to Text Mode.")
                    current_mode = "text"

            elif current_mode == "text":
                current_mode = text_interaction(language_code, stt_available)

        except KeyboardInterrupt:
            print("\n[Ctrl+C] Returning to mode menu...")
            current_mode = _ask_next_action(stt_available)

    print("\nShutting down. Goodbye!\n")


if __name__ == "__main__":
    main()
