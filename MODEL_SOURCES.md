# Model sources and download behavior

The GitHub folder contains application code, small model configuration files, and project data. Large model weights are fetched into local folders or the Hugging Face cache at runtime and are excluded by `.gitignore`.

| Feature | Model source | When weights download |
| --- | --- | --- |
| Chatbot embeddings | [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3) | When chatbot knowledge-base initialization starts. The code pins revision `d5ab3da48ec596cd78a50b27e52c7211b49d870f`. |
| Speech transcription | [IndicConformer Sherpa-ONNX exports](https://huggingface.co/parismitaglobalsolutions/indicconformer-sherpa-onnx) | English and all 22 supported Indian languages are fetched on first use of each language. The code pins revision `9721eb71eea141fae0982cfcdb9dd2e3d4953c4a`. The exports are based on AI4Bharat IndicConformer; credit belongs to AI4Bharat and the sherpa-onnx project. |
| English to Indic page translation | [IndicTrans2 int8 ONNX export](https://huggingface.co/hari31416/indictrans2-en-indic-dist-200M-ONNX-int8) | When `batch_translate_websites.py` or `translate_simulator_tour.py` needs to create/update translated output. Pinned revision: `1eaa43a3fb76f382f1b22c76e56f6ab4926ad68b`. |
| Indic to English translation | [IndicTrans2 int8 ONNX export](https://huggingface.co/hari31416/indictrans2-indic-en-dist-200M-ONNX-int8) | Downloaded with the page-translation model when translation setup requests both directions. Pinned revision: `a7ecdc0ba73148c6e1d051ca372332471d8aff4f`. |

The chatbot and document-vision language models are **Qwen3:8B** and **Qwen3-VL:8B**, served separately by [Ollama](https://ollama.com/). They are not stored in this repository and must be pulled with Ollama as described in `MODEL_SETUP.md`.

Keep an internet connection available for the first use of each Hugging Face model. Hugging Face caches completed downloads, so later starts reuse them. Do not commit downloaded weight files.
