"""Fetch Nivesh model files from pinned public Hugging Face repositories.

Models are downloaded only when their feature needs them. This keeps the
GitHub repository small while preserving the original local inference flow.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPEECH_ROOT = ROOT / "models"
SPEECH_REPO = "parismitaglobalsolutions/indicconformer-sherpa-onnx"
SPEECH_REVISION = "9721eb71eea141fae0982cfcdb9dd2e3d4953c4a"
# English plus all 22 Indian languages supported by the IndicConformer export.
# We download only the selected language model so a GitHub checkout stays small.
SPEECH_LANGUAGES = (
    "en", "as", "bn", "brx", "doi", "gu", "hi", "kn", "ks", "kok", "mai",
    "ml", "mni", "mr", "ne", "or", "pa", "sa", "sat", "sd", "ta", "te", "ur",
)

TRANSLATION_REPOS = {
    "model_en_to_indic": (
        "hari31416/indictrans2-en-indic-dist-200M-ONNX-int8",
        "1eaa43a3fb76f382f1b22c76e56f6ab4926ad68b",
    ),
    "model_indic_to_en": (
        "hari31416/indictrans2-indic-en-dist-200M-ONNX-int8",
        "a7ecdc0ba73148c6e1d051ca372332471d8aff4f",
    ),
}
TRANSLATION_FILES = [
    "config.json",
    "decoder_model.onnx",
    "decoder_shared.onnx.data",
    "decoder_with_past_model.onnx",
    "dict.SRC.json",
    "dict.TGT.json",
    "encoder_model.onnx",
    "encoder_model.onnx.data",
    "generation_config.json",
    "model.SRC",
    "model.TGT",
    "special_tokens_map.json",
    "tokenization_indictrans.py",
    "tokenizer_config.json",
    "tokenizer_meta.json",
    "tokenizer_src.json",
    "tokenizer_tgt.json",
]


def _hub():
    try:
        from huggingface_hub import hf_hub_download, snapshot_download
    except ImportError as exc:
        raise RuntimeError(
            "Hugging Face downloads need the project dependencies. "
            "Install them with: python -m pip install -r requirements.txt"
        ) from exc
    return hf_hub_download, snapshot_download


def ensure_speech_model(language_code: str, project_root: Path | None = None) -> tuple[Path, Path]:
    """Ensure the selected Sherpa-ONNX model and tokens exist locally."""
    code = (language_code or "").strip().lower()
    if code not in SPEECH_LANGUAGES:
        raise ValueError(f"Speech model is not configured for language code {code!r}.")

    root = Path(project_root or ROOT)
    model_root = root / "models"
    model_path = model_root / code / "model.int8.onnx"
    tokens_path = model_root / ("tokens1.txt" if code == "en" else "tokens.txt")
    if model_path.is_file() and tokens_path.is_file():
        return model_path, tokens_path

    hf_hub_download, _ = _hub()
    model_root.mkdir(parents=True, exist_ok=True)
    print(f"[models] Downloading the {code} speech model from Hugging Face…", flush=True)
    hf_hub_download(
        repo_id=SPEECH_REPO,
        filename=f"{code}/model.int8.onnx",
        revision=SPEECH_REVISION,
        local_dir=str(model_root),
    )

    if code == "en":
        source_tokens = Path(hf_hub_download(
            repo_id=SPEECH_REPO,
            filename="en/tokens.txt",
            revision=SPEECH_REVISION,
            local_dir=str(model_root),
        ))
        tokens_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_tokens, tokens_path)
    else:
        # Keep token IDs aligned with the matching Hugging Face ONNX export.
        hf_hub_download(
            repo_id=SPEECH_REPO,
            filename="tokens.txt",
            revision=SPEECH_REVISION,
            local_dir=str(model_root),
        )

    if not model_path.is_file() or not tokens_path.is_file():
        raise RuntimeError(f"Hugging Face download did not produce the {code} speech assets.")
    return model_path, tokens_path


def ensure_translation_model(model_name: str, project_root: Path | None = None) -> Path:
    """Download the small ONNX graph, tokenizers, and weights for one direction."""
    if model_name not in TRANSLATION_REPOS:
        raise ValueError(f"Unknown translation model: {model_name}")
    repo_id, revision = TRANSLATION_REPOS[model_name]
    folder = Path(project_root or ROOT) / "models_trans" / model_name
    required = (
        "encoder_model.onnx",
        "encoder_model.onnx.data",
        "decoder_model.onnx",
        "decoder_with_past_model.onnx",
        "decoder_shared.onnx.data",
        "tokenizer_src.json",
        "tokenizer_tgt.json",
        "tokenizer_meta.json",
        "generation_config.json",
    )
    if all((folder / name).is_file() for name in required):
        return folder

    _, snapshot_download = _hub()
    folder.mkdir(parents=True, exist_ok=True)
    print(f"[models] Downloading translation model {model_name} from Hugging Face…", flush=True)
    snapshot_download(
        repo_id=repo_id,
        revision=revision,
        local_dir=str(folder),
        allow_patterns=TRANSLATION_FILES,
    )
    missing = [name for name in required if not (folder / name).is_file()]
    if missing:
        raise RuntimeError(f"Translation model download is missing: {', '.join(missing)}")
    return folder


def prefetch_all() -> None:
    """Optional setup command for people who want all local model assets first."""
    for code in SPEECH_LANGUAGES:
        ensure_speech_model(code)
    for model_name in TRANSLATION_REPOS:
        ensure_translation_model(model_name)
    print("[models] BGE-M3 will download into the Hugging Face cache when chat starts.")
    print("[models] Qwen models are managed separately by Ollama; see MODEL_SETUP.md.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Nivesh speech and translation models.")
    parser.add_argument("--all", action="store_true", help="Download all 23 speech models and both translation models now.")
    parser.add_argument("--speech", choices=SPEECH_LANGUAGES, help="Download one speech language now.")
    parser.add_argument("--translation", action="store_true", help="Download both translation models now.")
    args = parser.parse_args()
    if args.all:
        prefetch_all()
    elif args.speech:
        ensure_speech_model(args.speech)
    elif args.translation:
        for model_name in TRANSLATION_REPOS:
            ensure_translation_model(model_name)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
