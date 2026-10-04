# Nivesh
HEAD
Hackathon Project
=======

Nivesh is an investor-awareness website with four tools: fraud detection, a plain-read disclosure reader, a consequence simulator, and a multilingual financial-literacy chatbot. The project includes pretranslated website pages and simulator tutorials.

## Run on Windows

1. Install Python 3.12 x64 and create a virtual environment:

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install --upgrade pip
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

2. Install [Ollama](https://ollama.com/download), open Terminal, and download the two required Qwen models:

   ```powershell
   ollama pull qwen3:8b
   ollama pull qwen3-vl:8b
   ```

3. Start the website from this folder:

   ```powershell
   .\.venv\Scripts\python.exe setup_and_run.py
   ```

   Keep the terminal open. The script opens the local website and prints the address to use.

The first run needs internet access. BGE-M3 downloads when the chatbot initializes. English and all 22 Indian speech-recognition models download from Hugging Face when each language is first selected; the app loads only the selected recognizer. Translation weights download only if you regenerate the pretranslated pages. Model sources, revisions, and download behavior are documented in `MODEL_SOURCES.md` and `MODEL_SETUP.md`.

To regenerate translated HTML pages, install the optional translator dependency with `python -m pip install -r requirements-translation.txt`. On Windows, that optional package needs Microsoft C++ Build Tools because it compiles a Cython extension. The already included translated pages and the main website do not need this extra install.

## Included project data

The `trading_docs` PDFs, `.xls` SEBI reference sheets, `scam_database.db`, and `chroma_db` are included. The application can recreate generated upload caches locally.

## Upload this folder to GitHub

Create an empty GitHub repository, then open Terminal in this folder and run:

```powershell
git init
git add .
git commit -m "Add Nivesh investor awareness website"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
git push -u origin main
```

Replace the remote address with your repository URL. `.gitignore` excludes downloaded model weights and runtime caches. Use Git from Terminal for the upload; GitHub's browser upload has lower per-file limits.

###Future scope:
1)Fraud SEBI certificates detection.
2)Multimodal Deepfake & Audio verification.
3)A bigger LLM model can be used instead of Qwen8b
4)Detecting edited official documents
5)Connecting this website to SEBI authority.
>>>>>>> 505b517 (initial)
