"""HTTP-safe speech generation for the browser chatbot.

Unlike listen1.py, this module does not initialize pygame or require an audio
device; it only returns MP3 bytes for the browser to play.
"""
from __future__ import annotations

from io import BytesIO
from functools import lru_cache


# Keep this explicit: unsupported selections must report an error instead of
# silently falling back to English speech.
@lru_cache(maxsize=128)
def generate_mp3(text: str, language_code: str) -> bytes:
    """Synthesize one answer segment in the requested language with gTTS."""
    normalized_language = (language_code or "").strip().lower().replace("_", "-")
    text = (text or "").strip()
    if not text:
        raise ValueError("There is no answer text to speak.")
    if len(text) > 4000:
        raise ValueError("This speech segment is too long. Try a shorter question.")

    try:
        from gtts import gTTS
        from gtts.lang import tts_langs
    except ImportError as exc:
        raise RuntimeError("Install the gTTS package to enable spoken chatbot answers.") from exc

    available = {code.lower(): code for code in tts_langs()}
    canonical_language = available.get(normalized_language)
    if not canonical_language:
        raise ValueError(
            f"gTTS has no voice for '{normalized_language or 'unknown'}'. "
            "The browser can try a matching voice installed on this device; it will not substitute English."
        )

    output = BytesIO()
    gTTS(text=text, lang=canonical_language, slow=False).write_to_fp(output)
    return output.getvalue()
