"""Pretranslate local HTML pages into AI4Bharat's 22 IndicTrans2 languages.

Run once with python batch_translate_websites.py --once, or add --force to
regenerate every language copy after changing source HTML. Outputs are saved in
translated_websites. Without --force, only missing copies are created.
"""
from __future__ import annotations

import argparse
import html
import logging
import re
import time
from pathlib import Path

from models.translate2 import LANGUAGE_MAP, load_translation_models, translate_english_to_indic
from html_text_extractor import _TextExtractor


ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "translated_websites"

# Add source names here when useful. Root-level HTML files are also discovered
# automatically, so new pages do not have to be added to this list.
HTML_FILES = [
    "index.html",
    "simulator.html",
    "terms-checker.html",
    "fraud-detector.html"
]
DISCOVER_NEW_HTML = True
SCAN_INTERVAL_SECONDS = 60

LANGUAGES = {code: tag for code, tag in LANGUAGE_MAP.items() if code != "en"}
OUTPUT_SUFFIX_RE = re.compile(r"-([a-z]{2,3})\.html$", re.IGNORECASE)
TAG_RE = re.compile(r"(<[^>]+>)")
WHITESPACE_START_RE = re.compile(r"^\s*")
WHITESPACE_END_RE = re.compile(r"\s*$")


def _logger() -> logging.Logger:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("batch_translate_websites")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s  %(levelname)s  %(message)s")
        file_handler = logging.FileHandler(OUTPUT_DIR / "batch_translate.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    return logger


def _is_generated_html(path: Path) -> bool:
    match = OUTPUT_SUFFIX_RE.search(path.name)
    return bool(match and match.group(1).lower() in LANGUAGES)


def source_pages() -> list[Path]:
    names = set(HTML_FILES)
    if DISCOVER_NEW_HTML:
        names.update(path.name for path in ROOT.glob("*.html"))

    pages = []
    for name in sorted(names):
        path = (ROOT / name).resolve()
        if path.parent != ROOT or path.suffix.lower() != ".html" or not path.is_file():
            continue
        if _is_generated_html(path):
            continue
        pages.append(path)
    return pages


def _translate_text_piece(text: str, engines: dict, lang_code: str) -> str:
    leading = WHITESPACE_START_RE.match(text).group(0)
    trailing = WHITESPACE_END_RE.search(text).group(0)
    end = len(text) - len(trailing) if trailing else len(text)
    core = text[len(leading):end]
    if not core:
        return text

    decoded = html.unescape(core)
    if not any(char.isalpha() for char in decoded):
        return text

    translated = translate_english_to_indic(engines, decoded, lang_code)
    if translated.startswith("Error:"):
        raise RuntimeError(translated)
    if not translated.strip():
        return text
    return leading + html.escape(translated.strip(), quote=False) + trailing


def _translate_mixed_html(text: str, engines: dict, lang_code: str) -> str:
    translated = []
    for piece in TAG_RE.split(text):
        if not piece:
            continue
        if piece.startswith("<") and piece.endswith(">"):
            translated.append(piece)
        else:
            translated.append(_translate_text_piece(piece, engines, lang_code))
    return "".join(translated)


def _set_html_language(match: re.Match, lang_code: str) -> str:
    attributes = re.sub(
        r'\s+lang\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]*)',
        "",
        match.group(1),
        flags=re.IGNORECASE,
    )
    return f'<html{attributes} lang="{lang_code}">'


def _translate_page(source_html: str, engines: dict, lang_code: str) -> str:
    extractor = _TextExtractor()
    extractor.feed_raw(source_html)
    result = source_html
    for segment in reversed(extractor.segments):
        translated = _translate_mixed_html(segment["text"], engines, lang_code)
        result = result[:segment["start"]] + translated + result[segment["end"]:]

    # Copies live one folder below their source; this keeps shared CSS, JS,
    # and image paths working when a translated copy is opened directly.
    if re.search(r"<head\b[^>]*>", result, flags=re.IGNORECASE):
        if not re.search(r"<base\b", result, flags=re.IGNORECASE):
            result = re.sub(
                r"(<head\b[^>]*>)",
                r'\1<base href="../">',
                result,
                count=1,
                flags=re.IGNORECASE,
            )
    else:
        result = '<base href="../">' + result

    return re.sub(
        r"<html\b([^>]*)>",
        lambda match: _set_html_language(match, lang_code),
        result,
        count=1,
        flags=re.IGNORECASE,
    )


def _output_path(source: Path, lang_code: str) -> Path:
    return OUTPUT_DIR / f"{source.stem}-{lang_code}{source.suffix.lower()}"


def translate_missing_outputs(engines: dict, logger: logging.Logger, force: bool = False) -> int:
    created = 0
    for source in source_pages():
        pending = [(code, _output_path(source, code)) for code in LANGUAGES]
        pending = [(code, path) for code, path in pending if force or not path.exists()]
        if not pending:
            continue

        logger.info("Translating %s into %d missing language copies", source.name, len(pending))
        original = source.read_text(encoding="utf-8", errors="replace")
        for code, destination in pending:
            try:
                translated = _translate_page(original, engines, code)
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary = destination.with_name(destination.name + ".tmp")
                temporary.write_text(translated, encoding="utf-8")
                temporary.replace(destination)
                logger.info("Created %s", destination.relative_to(ROOT))
                created += 1
            except Exception:
                logger.exception("Could not translate %s to %s; it will be retried", source.name, code)
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description="Watch local HTML pages and pretranslate them to Indic languages.")
    parser.add_argument("--once", action="store_true", help="Translate missing copies once, then exit.")
    parser.add_argument("--force", action="store_true", help="Regenerate every translated copy, even if it already exists.")
    parser.add_argument("--interval", type=int, default=SCAN_INTERVAL_SECONDS, help="Seconds between scans.")
    args = parser.parse_args()
    logger = _logger()

    if not source_pages():
        logger.error("No source HTML files found in %s", ROOT)
        return

    model_dir = ROOT / "models_trans"
    logger.info("Loading the offline AI4Bharat English-to-Indic model")
    engines = load_translation_models(
        en_to_indic_path=str(model_dir / "model_en_to_indic"),
        indic_to_en_path=str(model_dir / "model_indic_to_en"),
        include_indic_to_en=False,
    )

    force_first_scan = args.force
    while True:
        count = translate_missing_outputs(engines, logger, force=force_first_scan)
        logger.info("Scan complete: %d new translated page(s)", count)
        if args.once or force_first_scan:
            break
        force_first_scan = False
        try:
            time.sleep(max(5, args.interval))
        except KeyboardInterrupt:
            logger.info("Stopped by user")
            break


if __name__ == "__main__":
    main()
