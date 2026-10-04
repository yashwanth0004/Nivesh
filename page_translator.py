"""
page_translator.py  –  Website Page Translator using Qwen
============================================================
Translates all visible text in an HTML page (h1-h6, p, li, span,
label, button, a, td, th, caption, figcaption, blockquote) to a
chosen language using the already-loaded Qwen model.

USAGE (standalone CLI):
    python page_translator.py input.html te
    python page_translator.py input.html hi --out translated.html

USAGE (as a module — model must already be initialized):
    import model_7
    import page_translator

    model_7.initialize()   # done once at server startup

    with open("index.html", encoding="utf-8") as f:
        original_html = f.read()

    translated_html = page_translator.translate_html(original_html, lang_code="te")

    with open("index_te.html", "w", encoding="utf-8") as f:
        f.write(translated_html)
"""

import re
import sys
import argparse
from html.parser import HTMLParser
from html import escape, unescape

import model_7

# ─── Tags whose text content should be translated ────────────────────────────
TRANSLATE_TAGS = {
    "h1", "h2", "h3", "h4", "h5", "h6",
    "p", "li", "span", "label", "button",
    "a", "td", "th", "caption", "figcaption",
    "blockquote", "cite", "legend", "summary", "strong", "b",
    "em", "i", "small", "option",
}

# ─── Tags to skip entirely (no translation inside) ───────────────────────────
SKIP_TAGS = {"script", "style", "code", "pre", "svg", "math", "noscript"}


# ─────────────────────────────────────────────────────────────────────────────
# HTML Parser that collects text segments and their positions
# ─────────────────────────────────────────────────────────────────────────────
class _TextExtractor(HTMLParser):
    """Parses HTML and records (start, end, text) of translatable text nodes."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.segments   = []   # list of {"start": int, "end": int, "text": str}
        self._raw       = ""
        self._skip_depth = 0
        self._active_tag = None
        self._translate_depth = 0
        self._buf_start = None

    def feed_raw(self, raw: str):
        self._raw = raw
        self.feed(raw)

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self._skip_depth += 1
        elif tag in TRANSLATE_TAGS and self._skip_depth == 0:
            self._translate_depth += 1
            if self._translate_depth == 1:
                # Record where the text inside this tag starts
                pos = self.getpos()   # (line, col) — we'll use offset instead
                # Use a regex to find the actual char offset of this tag's closing >
                # We track by rebuilding offset from the raw string
                self._find_content_start(tag, attrs)

    def _find_content_start(self, tag, attrs):
        # We need the character offset of the end of this opening tag in _raw.
        # HTMLParser.getpos() gives (line, col) — convert to offset.
        line, col = self.getpos()
        lines = self._raw.splitlines(keepends=True)
        offset = sum(len(l) for l in lines[:line - 1]) + col
        # Find the closing '>' of this opening tag from offset
        close = self._raw.find(">", offset)
        if close != -1:
            self._buf_start = close + 1

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in TRANSLATE_TAGS and self._skip_depth == 0:
            if self._translate_depth == 1 and self._buf_start is not None:
                # Find the offset of the closing tag
                line, col = self.getpos()
                lines = self._raw.splitlines(keepends=True)
                end_offset = sum(len(l) for l in lines[:line - 1]) + col
                text_slice = self._raw[self._buf_start:end_offset]
                # Only translate if there is actual visible text (not just tags)
                visible = re.sub(r"<[^>]+>", "", text_slice).strip()
                if visible:
                    self.segments.append({
                        "start": self._buf_start,
                        "end":   end_offset,
                        "text":  text_slice,
                    })
                self._buf_start = None
            self._translate_depth = max(0, self._translate_depth - 1)

    def handle_data(self, data):
        # Catch visible text in ordinary containers (for example div, small,
        # and custom elements) that are not wrapped in a dedicated text tag.
        if not data.strip() or self._skip_depth or self._translate_depth:
            return
        line, col = self.getpos()
        lines = self._raw.splitlines(keepends=True)
        start = sum(len(part) for part in lines[:line - 1]) + col
        self.segments.append({"start": start, "end": start + len(data), "text": data})


# ─────────────────────────────────────────────────────────────────────────────
# Translate a single piece of plain/mixed text using Qwen
# ─────────────────────────────────────────────────────────────────────────────
def _translate_chunk(text: str, lang_name: str) -> str:
    """
    Ask Qwen to translate `text` into `lang_name`.
    Strips HTML tags before translating, then re-inserts them naively.
    For best results the text should be short (one sentence to one paragraph).
    """
    # Keep inline markup in place with stable markers while translating text.
    # This protects links, emphasis, and other nested elements from being lost.
    leading = text[:len(text) - len(text.lstrip())]
    trailing = text[len(text.rstrip()):]
    core = text[len(leading):len(text) - len(trailing) if trailing else len(text)]
    inner_tags = []
    def mark_tag(match):
        inner_tags.append(match.group(0))
        return f"NIVESHTAG{len(inner_tags)-1}TOKEN"
    visible = re.sub(r"<[^>]+>", mark_tag, core).strip()

    if not visible:
        return text  # nothing to translate

    prompt = (
        f"Translate the following text accurately into {lang_name}. "
        f"Output ONLY the translated text, nothing else. Preserve every token like NIVESHTAG0TOKEN exactly and in its original order. "
        f"Preserve the original meaning completely.\n\n"
        f"Text to translate:\n{visible}"
    )

    # Use Qwen directly (bypass RAG, topic check, history)
    try:
        from langchain_core.prompts import PromptTemplate
        tmpl  = PromptTemplate.from_template("{prompt}")
        chain = tmpl | model_7.llm
        translated = ""
        for chunk in chain.stream({"prompt": prompt}):
            translated += chunk
        translated = translated.strip()
    except Exception as e:
        print(f"  [Translation error]: {e}")
        return text   # fallback: keep original

    # Put the original tags back at their translated positions.
    for i, tag in enumerate(inner_tags):
        translated = re.sub(rf"NIVESHTAG{i}TOKEN", lambda _match, original=tag: original, translated, count=1)
    return leading + translated + trailing


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC: translate_html()
# ─────────────────────────────────────────────────────────────────────────────
def translate_html(html: str, lang_code: str = "te") -> str:
    """
    Translate all visible text in `html` to the language identified by
    `lang_code` using the already-loaded Qwen model.

    Args:
        html:      Full HTML string of the page.
        lang_code: Language code, e.g. "te", "hi", "en".

    Returns:
        A new HTML string with all visible text translated.
    """
    if model_7.llm is None:
        raise RuntimeError("Call model_7.initialize() before translate_html().")

    lang_name = model_7._get_language_name(lang_code)
    print(f"\n[Translator] Translating page to {lang_name}...")

    # Extract translatable segments
    extractor = _TextExtractor()
    extractor.feed_raw(html)
    segments = extractor.segments

    if not segments:
        print("[Translator] No translatable text segments found.")
        return html

    print(f"[Translator] Found {len(segments)} text segments to translate.")

    # Translate from back to front so character offsets stay valid
    result = html
    for i, seg in enumerate(reversed(segments), 1):
        original_inner = seg["text"]
        print(f"  [{i}/{len(segments)}] Translating: {original_inner[:60].strip()}...")
        translated_inner = _translate_chunk(original_inner, lang_name)
        result = result[:seg["start"]] + translated_inner + result[seg["end"]:]

    print(f"[Translator] Done. Page translated to {lang_name}.\n")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# CLI usage
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Translate an HTML page using Qwen.")
    parser.add_argument("input",  help="Path to the input HTML file.")
    parser.add_argument("lang",   help="Target language code: te, hi, en, ta, kn, etc.")
    parser.add_argument("--out",  default=None,
                        help="Output file path (default: input_<lang>.html).")
    args = parser.parse_args()

    if args.out is None:
        base = args.input.rsplit(".", 1)
        args.out = f"{base[0]}_{args.lang}.html" if len(base) == 2 else f"{args.input}_{args.lang}"

    print("Loading Qwen model...")
    model_7.initialize()

    with open(args.input, encoding="utf-8") as f:
        original = f.read()

    translated = translate_html(original, lang_code=args.lang)

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(translated)

    print(f"Translated HTML saved to: {args.out}")
