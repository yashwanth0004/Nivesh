# Nivesh install checklist

`requirements.txt` installs the Python packages. The following runtime and model files are separate downloads; pip cannot install these weights.

## 1. Python

On Windows, install Python 3.12 x64 for the complete dependency set. PyTorch's current Windows guidance supports Python 3.9–3.12; Python 3.14 can therefore fail when installing the vision/embedding dependencies. See the [PyTorch Windows install guide](https://docs.pytorch.org/get-started/locally/).

From PowerShell in the project folder:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Use the same `.venv` Python to start the website:

```powershell
.\.venv\Scripts\python.exe setup_and_run.py
```

## 2. Ollama and Qwen weights

Install the [Ollama app](https://ollama.com/download), start it, then download both models in Terminal:

```powershell
ollama pull qwen3:8b
ollama pull qwen3-vl:8b
```

The chatbot uses `qwen3:8b`; image/PDF fraud analysis uses `qwen3-vl:8b`. Qwen3-VL requires Ollama 0.12.7 or newer according to its [Ollama model page](https://ollama.com/library/qwen3-vl). The listed quantized weights are about 5.2 GB and 6.1 GB respectively, before caches and application data; leave additional disk space. Start Ollama before `setup_and_run.py`.

## 3. Models downloaded from Hugging Face

Model weights are excluded from this GitHub-sized folder. The application fetches the needed weights into local model folders or the standard Hugging Face cache the first time each feature needs them. Keep an internet connection available for that first use.

- **Chatbot embeddings:** `BAAI/bge-m3` downloads into the Hugging Face cache when the chatbot initializes. This model is about 2.3 GB, so the first chatbot startup can take time and needs that much free disk space.
- **Voice transcription:** English plus all 22 supported Indian language models download from Hugging Face when a language is first selected. Only the selected model loads into memory; expect roughly 170–190 MB of disk per language model, with extra memory while a recognizer is active. A language selection requires internet access on its first use; later uses reuse the local download.
- **Website translation:** the existing translated HTML pages and simulator tutorial translations are already included. Running `batch_translate_websites.py` or `translate_simulator_tour.py` downloads the relevant ONNX translation models on first use (about 600 MB total for both directions).
- Regenerating translated pages additionally needs `python -m pip install -r requirements-translation.txt`. On Windows, this optional package compiles a Cython extension and requires Microsoft C++ Build Tools. The pretranslated pages do not need it.
- The speech and translation downloads use pinned Hugging Face revisions. Their repository links and credits are listed in `MODEL_SOURCES.md`.
- `chroma_db/`, `trading_docs/`, `scam_database.db`, and the `.xls` SEBI reference sheets are project data and are included. Runtime upload caches and logs are regenerated locally.

## 4. Optional device requirements

- For GPU acceleration with Hugging Face/PyTorch, install the PyTorch build matching the computer's NVIDIA driver/CUDA version using the official selector above. Ollama manages its own model runtime separately.
- `main_app.py` microphone/audio playback needs a working microphone and audio output. The browser website's gTTS voice output needs internet access.
- No separate Tesseract installation is used by the current fraud checker.
