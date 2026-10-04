"""
listen1.py  –  Text-to-Speech module using gTTS + pygame
==========================================================
Exposes THREE functions for the two-thread TTS pipeline:
  generate_audio_bytes(text, lang_code) -> BytesIO   [network call, slow]
  play_audio_bytes(mp3_fp)                            [CPU/GPU, fast]
  speak_text(text, lang_code)                         [convenience: both at once]

main_app.py uses generate + play in separate threads so audio generation
for sentence N+1 overlaps with playback of sentence N — no gaps.
"""

import io
import pygame

# ── pygame mixer init once at module load ─────────────────────────────────────
# stereo, 44100 Hz, buffer=2048 reduces audio artifacts vs 512
pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)

def _clean_lang(lang_code: str) -> str:
    code = (lang_code or "").lower().strip().replace("_", "-")
    from gtts.lang import tts_langs
    available = {key.lower(): key for key in tts_langs()}
    canonical = available.get(code)
    if not canonical:
        raise ValueError(
            f"gTTS does not support speech language '{code or 'unknown'}'. "
            "Choose a language with a matching installed TTS voice; English will not be used as a fallback."
        )
    return canonical


def generate_audio_bytes(text: str, lang_code: str = "en") -> io.BytesIO | None:
    """
    Convert text → MP3 bytes in memory using gTTS (makes a network call).
    Returns a BytesIO object seeked to position 0, or None on failure.
    Call this in a background thread so it doesn't block playback.
    """
    text = text.strip()
    if not text:
        return None

    try:
        from gtts import gTTS
        lang = _clean_lang(lang_code)
        mp3_fp = io.BytesIO()
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.write_to_fp(mp3_fp)
        mp3_fp.seek(0)
        return mp3_fp
    except Exception as e:
        print(f"[TTS generate error]: {e}")
        return None


def play_audio_bytes(mp3_fp: io.BytesIO) -> None:
    """
    Play a pre-generated MP3 BytesIO buffer through the speakers.
    Blocks until playback finishes. Call this in the player thread.
    Keeps a local reference to `sound` so pygame doesn't GC it mid-play.
    """
    if mp3_fp is None:
        return
    try:
        mp3_fp.seek(0)
        sound = pygame.mixer.Sound(mp3_fp)  # local ref = no GC during play
        channel = sound.play()
        while channel is not None and channel.get_busy():
            pygame.time.Clock().tick(15)
    except Exception as e:
        print(f"[TTS play error]: {e}")


def speak_text(text: str, lang_code: str = "en") -> None:
    """
    Convenience wrapper: generate + play in one blocking call.
    Use this for simple one-shot TTS (text mode or short messages).
    """
    mp3_fp = generate_audio_bytes(text, lang_code)
    play_audio_bytes(mp3_fp)


# ── STANDALONE TEST ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    lines = []
    print("Enter text lines to speak (type END when finished):")
    while True:
        try:
            line = input()
            if line.strip() == "END":
                break
            lines.append(line)
        except EOFError:
            break

    full_text = " ".join(lines)
    if full_text.strip():
        lang = input("Enter language code (e.g., en, hi, te): ").strip()
        speak_text(full_text, lang_code=lang)
