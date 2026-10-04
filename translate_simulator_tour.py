"""Pretranslate the simulator's interactive tutorial into all supported Indic languages."""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

from batch_translate_websites import LANGUAGES, _translate_mixed_html
from models.translate2 import load_translation_models, translate_english_to_indic


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "simulator.js"
OUTPUT = ROOT / "simulator_tour_translations.json"
STEP_RE = re.compile(
    r"\{\s*id:\s*'(?P<id>[^']+)',\s*title:\s*'(?P<title>[^']+)',\s*body:\s*`(?P<body>[\s\S]*?)`",
)


def translate_text(engines: dict, text: str, language: str) -> str:
    result = translate_english_to_indic(engines, text, language).strip()
    if not result or result.startswith("Error:"):
        raise RuntimeError(f"Translation failed for {language}: {text[:80]}")
    return result


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    steps = [match.groupdict() for match in STEP_RE.finditer(source)]
    if len(steps) != 12:
        raise RuntimeError(f"Expected 12 tutorial steps in {SOURCE.name}; found {len(steps)}")

    engines = load_translation_models(
        en_to_indic_path=str(ROOT / "models_trans" / "model_en_to_indic"),
        indic_to_en_path=str(ROOT / "models_trans" / "model_indic_to_en"),
        include_indic_to_en=False,
    )

    ui_labels = {"step": "Step", "of": "of", "next": "Next", "finish": "Finish", "end": "End Tutorial"}
    translations = {}
    for code in LANGUAGES:
        print(f"Translating simulator tutorial: {code}", flush=True)
        translations[code] = {
            "ui": {key: translate_text(engines, value, code) for key, value in ui_labels.items()},
            "steps": {},
        }
        for step in steps:
            translations[code]["steps"][step["id"]] = {
                "title": html.escape(translate_text(engines, step["title"], code), quote=False),
                "body": _translate_mixed_html(step["body"], engines, code),
            }

    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(translations, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(OUTPUT)
    print(f"Wrote translations for {len(translations)} languages to {OUTPUT.name}", flush=True)


if __name__ == "__main__":
    main()
