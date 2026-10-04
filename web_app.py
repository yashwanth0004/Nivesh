"""Local web front end for the Nivesh investor education tools.

Run with: python web_app.py
The website AI models begin loading in a background thread when the server starts.
"""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, urljoin, quote
from pathlib import Path
import json
import threading
import urllib.request
import urllib.error
import ipaddress
import socket
import re
import hashlib
import os
import shutil
import subprocess
import sys
import time
from http.cookies import SimpleCookie
from html import escape

ROOT = Path(__file__).resolve().parent
TRANSLATED_DIR = ROOT / "translated_websites"
SUPPORTED_WEB_LANGUAGES = {
    "en", "as", "bn", "brx", "doi", "gu", "hi", "kn", "ks", "kok", "mai",
    "ml", "mni", "mr", "ne", "or", "pa", "sa", "sat", "sd", "ta", "te", "ur",
}
_model_lock = threading.Lock()
_generation_lock = threading.Lock()
_generation_events_lock = threading.Lock()
_generation_cancel_events = {}
_model_ready = False
_model_status = "not_started"
_model_error = None
_vision_status = "not_started"
_vision_error = None
_ollama_process = None
_fraud_lock = threading.Lock()
_fraud_process = None
_fraud_status = "not_started"
_fraud_error = None
_fraud_port = 8001
FRAUD_API_VERSION = "2026-10-03.11"


def ensure_ollama_server():
    """Start the local Ollama API if it is installed but not already running."""
    global _ollama_process
    api_url = "http://127.0.0.1:11434/api/tags"

    def is_available():
        try:
            with urllib.request.urlopen(api_url, timeout=2):
                return True
        except urllib.error.HTTPError:
            # An HTTP response means the server is alive, even if this endpoint
            # returned an error status.
            return True
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    if is_available():
        return

    executable = shutil.which("ollama")
    # The Windows installer commonly places Ollama here without adding it to
    # PATH. Resolve that default location so a fresh terminal can still launch it.
    if not executable and os.name == "nt":
        candidates = []
        for base in (os.environ.get("LOCALAPPDATA"), str(Path.home() / "AppData" / "Local")):
            if base:
                candidates.extend((
                    Path(base) / "Programs" / "Ollama" / "ollama.exe",
                    Path(base) / "Programs" / "Ollama" / "ollama",
                ))
        executable = next((str(candidate) for candidate in candidates if candidate.is_file()), None)
    if not executable:
        raise RuntimeError("Ollama is not running and ollama.exe was not found on PATH or in the standard Windows install folder.")

    if _ollama_process is None or _ollama_process.poll() is not None:
        kwargs = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
        }
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        _ollama_process = subprocess.Popen([executable, "serve"], **kwargs)

    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if is_available():
            return
        if _ollama_process.poll() is not None:
            break
        time.sleep(1)
    raise RuntimeError("Could not start the local Ollama service on 127.0.0.1:11434.")


def ensure_model():
    global _model_ready, _model_status, _model_error
    if not _model_ready:
        with _model_lock:
            if not _model_ready:
                _model_status = "loading"
                try:
                    ensure_ollama_server()
                    import model_7
                    model_7.initialize()
                    # Force Ollama to load Qwen now, rather than on the first chat.
                    # Keep this in the startup worker so the website remains responsive.
                    model_7.llm.invoke(
                        "Reply with READY.",
                        options={"num_predict": 1},
                    )
                    _model_ready = True
                    _model_status = "ready"
                    _model_error = None
                except Exception as exc:
                    _model_status = "error"
                    _model_error = str(exc)
                    raise
    import model_7
    return model_7


def preload_model():
    global _vision_status, _vision_error
    _vision_status = "loading"
    _vision_error = None
    try:
        ensure_ollama_server()
        # Start the fraud/vision service with the website instead of waiting
        # until someone first opens the Fraud Checker page.
        start_fraud_backend()
        deadline = time.monotonic() + 30 * 60
        while time.monotonic() < deadline:
            status = fraud_backend_status()
            if status.get("state") == "ready":
                _vision_status = "ready"
                _vision_error = None
                print("[web] Fraud API and qwen3-vl:8b are loaded and ready.")
                break
            if status.get("state") == "error":
                raise RuntimeError(status.get("error") or "Fraud AI startup failed.")
            time.sleep(2)
        else:
            raise RuntimeError("Fraud API and qwen3-vl:8b did not finish loading within 30 minutes.")
    except Exception as exc:
        _vision_status = "error"
        _vision_error = str(exc)
        print(f"[web] Fraud API/qwen3-vl:8b startup failed: {exc}")

    # Load the chat model and local embedding database during website startup,
    # so the first chatbot request does not trigger a cold model load.
    try:
        ensure_model()
        print("[web] qwen3:8b chatbot model and knowledge base are loaded.")
    except Exception as exc:
        print(f"[web] qwen3:8b chatbot startup failed: {exc}")


def start_fraud_backend():
    """Use a current fraud API, starting one on a free port if an old copy is running."""
    global _fraud_process, _fraud_status, _fraud_error, _fraud_port
    # Adopt a compatible API if one is already running. A previous website run
    # may have left an older fraud API on 8001; never silently route to it.
    for candidate_port in (8001, 8005, 8006, 8007, 8008, 8009, 8010, 8011, 8012):
        health_url = f"http://127.0.0.1:{candidate_port}/health"
        try:
            with urllib.request.urlopen(health_url, timeout=0.5) as response:
                health = json.loads(response.read().decode("utf-8"))
            if health.get("api_version") == FRAUD_API_VERSION:
                _fraud_port = candidate_port
                _fraud_status = "ready" if health.get("sebi_engine_loaded") and health.get("risk_engine_loaded") else "loading"
                _fraud_error = None
                return
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
            pass

    if _fraud_process is not None:
        exit_code = _fraud_process.poll()
        if exit_code is None:
            _fraud_status = "loading"
            return
        _fraud_status = "error"
        _fraud_error = f"Fraud backend exited with code {exit_code}; see fraud_backend.log."
        return

    selected_port = None
    for candidate_port in (8001, 8005, 8006, 8007, 8008, 8009, 8010, 8011, 8012):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind(("127.0.0.1", candidate_port))
            selected_port = candidate_port
            break
        except OSError:
            continue
        finally:
            probe.close()
    if selected_port is None:
        _fraud_status = "error"
        _fraud_error = "No free local port is available for the fraud API."
        return
    _fraud_port = selected_port

    with _fraud_lock:
        try:
            environment = os.environ.copy()
            environment["NIVESH_FRAUD_PORT"] = str(_fraud_port)
            log_path = ROOT / "fraud_backend.log"
            log_file = open(log_path, "a", encoding="utf-8")
            launch_options = {
                "cwd": str(ROOT),
                "env": environment,
                "stdin": subprocess.DEVNULL,
                "stdout": log_file,
                "stderr": subprocess.STDOUT,
            }
            if os.name == "nt":
                launch_options["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            _fraud_process = subprocess.Popen(
                [sys.executable, str(ROOT / "unified_api.py")],
                **launch_options,
            )
            _fraud_status = "loading"
            _fraud_error = None
        except Exception as exc:
            _fraud_status = "error"
            _fraud_error = str(exc)
            print(f"[web] Could not start fraud backend: {exc}")


def fraud_backend_status():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{_fraud_port}/health", timeout=2) as response:
            health = json.loads(response.read().decode("utf-8"))
        if health.get("api_version") != FRAUD_API_VERSION:
            return {"state": "error", "error": "The fraud API version is out of date. Restart the website from setup_and_run.py."}
        ready = bool(health.get("sebi_engine_loaded") and health.get("risk_engine_loaded"))
        return {"state": "ready" if ready else "loading", "health": health, "port": _fraud_port}
    except Exception as exc:
        if _fraud_process is not None and _fraud_process.poll() is None:
            return {"state": "loading"}
        return {"state": "error", "error": _fraud_error or str(exc)}


def safe_public_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Enter a full http:// or https:// website address.")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, None)
        if any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise ValueError("Private and local network addresses cannot be translated.")
    except socket.gaierror as exc:
        raise ValueError("The website address could not be resolved.") from exc
    return parsed


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        served_path = urlparse(self.path).path.lower()
        if served_path.endswith(".html") or served_path == "/" or served_path == "/chat-widget.js":
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def proxy_fraud_post(self):
        size = int(self.headers.get("Content-Length", "0"))
        if size <= 0 or size > 27 * 1024 * 1024:
            self.send_json(413 if size > 27 * 1024 * 1024 else 400, {"detail": "Upload a non-empty file smaller than 25 MB."})
            return
        payload = self.rfile.read(size)
        request = urllib.request.Request(
            f"http://127.0.0.1:{_fraud_port}" + urlparse(self.path).path,
            data=payload,
            headers={"Content-Type": self.headers.get("Content-Type", "application/octet-stream")},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=1800) as response:
                status = response.status
                content_type = response.headers.get("Content-Type", "application/json; charset=utf-8")
                content_disposition = response.headers.get("Content-Disposition")
                response_body = response.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
            content_type = exc.headers.get("Content-Type", "application/json; charset=utf-8")
            content_disposition = exc.headers.get("Content-Disposition")
            response_body = exc.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            self.send_json(503, {"detail": f"Fraud API is not ready: {exc}. See fraud_backend.log."})
            return
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if content_disposition:
            self.send_header("Content-Disposition", content_disposition)
        self.send_header("Content-Length", str(len(response_body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(response_body)

    def send_html(self, content):
        data = content.encode("utf-8") if isinstance(content, str) else content
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def save_translation(self, cache_path, content):
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_name(cache_path.name + f".{threading.get_ident()}.tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(cache_path)

    def read_json(self):
        size = int(self.headers.get("Content-Length", "0"))
        if size > 2_000_000:
            raise ValueError("Request is too large.")
        return json.loads(self.rfile.read(size).decode("utf-8"))

    def send_chat_speech(self):
        body = self.read_json()
        text = str(body.get("text", "")).strip()
        language = str(body.get("lang", "en")).strip().lower()
        try:
            from web_tts import generate_mp3
            audio = generate_mp3(text, language)
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
            return
        except Exception as exc:
            self.send_json(502, {"error": f"Could not create {language} speech. Check the internet connection and gTTS setup: {exc}"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(len(audio)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(audio)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/language/"):
            # Resolve a language choice on the server rather than relying on
            # stale browser copies or client-side filename guessing. This also
            # works immediately after translated_websites is regenerated.
            parts = parsed.path.strip("/").split("/", 2)
            if len(parts) != 3 or parts[1].lower() not in SUPPORTED_WEB_LANGUAGES:
                self.send_error(400, "Choose a supported website language.")
                return
            language, source_name = parts[1].lower(), parts[2]
            if Path(source_name).name != source_name or not source_name.lower().endswith(".html"):
                self.send_error(400, "The requested page is not supported for language switching.")
                return
            source_path = ROOT / source_name
            if not source_path.is_file():
                self.send_error(404, "The original website page could not be found.")
                return
            query = f"?{parsed.query}" if parsed.query else ""
            if language == "en":
                destination = "/" if source_name.lower() == "index.html" else "/" + source_name
            else:
                translated_path = TRANSLATED_DIR / f"{Path(source_name).stem}-{language}.html"
                if not translated_path.is_file():
                    self.send_error(
                        503,
                        f"The {language} copy of {source_name} is not ready. Run python batch_translate_websites.py --once, then try again.",
                    )
                    return
                destination = "/translated_websites/" + translated_path.name
            self.send_response(302)
            self.send_header("Location", destination + query)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if parsed.path in {"/terms", "/terms/", "/terms-checker.html"}:
            start_fraud_backend()
            language = self.get_language()
            translated_path = TRANSLATED_DIR / f"terms-checker-{language}.html"
            if language != "en" and translated_path.is_file():
                self.send_response(302)
                self.send_header("Location", "/translated_websites/" + translated_path.name)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            try:
                self.send_html((ROOT / "terms-checker.html").read_text(encoding="utf-8"))
            except OSError as exc:
                self.send_error(500, f"Could not load Terms & Conditions Review: {exc}")
            return
        if parsed.path.startswith("/translated_websites/terms-checker-"):
            start_fraud_backend()
        if parsed.path in {"/fraud", "/fraud/"}:
            start_fraud_backend()
            language = self.get_language()
            if language != "en":
                translated_path = TRANSLATED_DIR / f"fraud-detector-{language}.html"
                if translated_path.is_file():
                    self.send_response(302)
                    self.send_header("Location", "/translated_websites/" + translated_path.name)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
            try:
                self.send_html((ROOT / "fraud-detector.html").read_text(encoding="utf-8"))
            except OSError as exc:
                self.send_error(500, f"Could not load Fraud Checker: {exc}")
            return
        if parsed.path == "/api/status":
            self.send_json(200, {
                "model": _model_status,
                "error": _model_error,
                "vision_model": _vision_status,
                "vision_error": _vision_error,
            })
            return
        if parsed.path == "/api/fraud/status":
            start_fraud_backend()
            self.send_json(200, fraud_backend_status())
            return
        if parsed.path == "/fraud-detector.html":
            start_fraud_backend()
            language = self.get_language()
            if language != "en":
                translated_path = TRANSLATED_DIR / f"fraud-detector-{language}.html"
                if translated_path.is_file():
                    self.send_response(302)
                    self.send_header("Location", "/translated_websites/" + translated_path.name)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
        if parsed.path == "/browse":
            try:
                target = parse_qs(parsed.query).get("url", [""])[0]
                lang = self.get_language()
                address = urlparse(target)
                if address.scheme not in ("http", "https") or not address.hostname:
                    raise ValueError("Enter a full http:// or https:// website address.")
                external_key = hashlib.sha256(f"{lang}\n{target}".encode("utf-8")).hexdigest()
                external_cache = TRANSLATED_DIR / "external" / lang / f"{external_key}.html"
                if lang != "en" and external_cache.is_file():
                    self.send_html(external_cache.read_text(encoding="utf-8"))
                    return
                safe_public_url(target)
                request = urllib.request.Request(target, headers={"User-Agent": "Nivesh-Learning/1.0"})
                with urllib.request.urlopen(request, timeout=25) as response:
                    final_url = response.geturl()
                    safe_public_url(final_url)
                    if "text/html" not in response.headers.get("Content-Type", ""):
                        raise ValueError("This viewer can open HTML webpages.")
                    source = response.read(4_000_000).decode(response.headers.get_content_charset() or "utf-8", errors="replace")
                source = re.sub(r"(<head\b[^>]*>)", lambda m: m.group(1) + f'<base href="{escape(final_url, quote=True)}">', source, count=1, flags=re.I)
                def proxy_link(match):
                    value = match.group(3).strip()
                    if not value or value.startswith(("#", "mailto:", "tel:", "javascript:", "data:", "blob:")):
                        return match.group(0)
                    absolute = urljoin(final_url, value)
                    if urlparse(absolute).scheme not in ("http", "https"):
                        return match.group(0)
                    return f'{match.group(1)}{match.group(2)}/browse?url={quote(absolute, safe="")}{match.group(2)}'
                source = re.sub(r'(?is)(<a\b[^>]*?\bhref\s*=\s*)(["\'])(.*?)\2', proxy_link, source)
                if lang != "en":
                    ensure_model()
                    import page_translator
                    source = page_translator.translate_html(source, lang)
                    self.save_translation(external_cache, source)
                self.send_html(source)
                return
            except Exception as exc:
                self.send_error(400, f"Could not open that webpage: {exc}")
                return

        path = ROOT / ("index.html" if parsed.path == "/" else parsed.path.lstrip("/"))
        try:
            resolved = path.resolve()
            is_prebuilt_output = resolved.is_relative_to(TRANSLATED_DIR.resolve())
            if not is_prebuilt_output and resolved.is_relative_to(ROOT) and resolved.suffix.lower() == ".html" and resolved.is_file():
                lang = self.get_language()
                if lang != "en":
                    translated_path = TRANSLATED_DIR / f"{resolved.stem}-{lang}{resolved.suffix.lower()}"
                    if translated_path.is_file():
                        self.send_response(302)
                        self.send_header("Location", "/translated_websites/" + translated_path.name)
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    self.send_error(
                        503,
                        f"The {lang} translation of {resolved.name} is missing. Run python batch_translate_websites.py --once, then reload this page.",
                    )
                    return
        except (OSError, ValueError):
            pass
        super().do_GET()

    def get_language(self):
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        candidate = cookie.get("nivesh_lang")
        code = candidate.value.lower() if candidate else "en"
        return code if code in SUPPORTED_WEB_LANGUAGES else "en"

    def do_POST(self):
        # Accept a trailing slash as well; browsers/proxies may preserve one
        # when calling API routes from nested/translated pages.
        route = urlparse(self.path).path.rstrip("/") or "/"
        content_type = self.headers.get("Content-Type", "").lower()
        if route in {"/api/chat/speech", "/api/speech", "/api/tts"}:
            try:
                self.send_chat_speech()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, socket.timeout):
                return
            except Exception as exc:
                try:
                    self.send_json(400, {"error": str(exc)})
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, socket.timeout):
                    pass
            return
        upload_routes = {
            "/api/v1/full-audit", "/api/v1/verify-sebi", "/api/v2/audit-claim",
            "/api/v1/terms-audit", "/api/v1/sebi-complaint-draft", "/api/v1/transcribe-voice",
        }
        if content_type.startswith("multipart/form-data") and route not in upload_routes:
            self.send_json(400, {
                "detail": "This website server does not recognize the audio upload route. Stop the older website and restart it with python setup_and_run.py, then open the URL printed in Terminal."
            })
            return
        if route == "/api/chat/stop":
            try:
                body = self.read_json()
                request_id = str(body.get("request_id", ""))
                with _generation_events_lock:
                    cancel_event = _generation_cancel_events.get(request_id)
                if cancel_event is not None:
                    cancel_event.set()
                self.send_json(200, {"success": True, "stopping": cancel_event is not None})
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, socket.timeout):
                return
            except Exception as exc:
                try:
                    self.send_json(400, {"error": str(exc)})
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, socket.timeout):
                    pass
            return
        if route in upload_routes:
            self.proxy_fraud_post()
            return
        stream_started = False
        cancel_event = None
        request_id = ""
        try:
            body = self.read_json()
            if route == "/api/chat":
                question = str(body.get("message", "")).strip()
                if not question:
                    raise ValueError("Type a question first.")
                request_id = str(body.get("request_id", "")) or hashlib.sha256(
                    f"{threading.get_ident()}:{time.monotonic_ns()}".encode("ascii")
                ).hexdigest()
                cancel_event = threading.Event()
                with _generation_events_lock:
                    _generation_cancel_events[request_id] = cancel_event
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-transform")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()
                stream_started = True
                self.wfile.write((json.dumps({"type": "status", "text": "Connected. Loading the local model if needed…"}, ensure_ascii=False) + "\n").encode("utf-8"))
                self.wfile.flush()
                model = ensure_model()
                with _generation_lock:
                    for chunk in model.stream_response_chunks(
                        question,
                        lang_code=body.get("lang", "en"),
                        cancel_event=cancel_event,
                    ):
                        if isinstance(chunk, dict) and chunk.get("type") in {"reset", "stopped", "error", "loop_stopped"}:
                            event = chunk
                        else:
                            event = {"type": "chunk", "text": str(chunk)}
                        line = json.dumps(event, ensure_ascii=False) + "\n"
                        self.wfile.write(line.encode("utf-8"))
                        self.wfile.flush()
                self.wfile.write(b'{"type":"done"}\n')
                self.wfile.flush()
                return
            self.send_json(404, {"error": "Unknown endpoint."})
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, socket.timeout):
            if cancel_event is not None:
                cancel_event.set()
            # Browsers and security software sometimes close a streamed request;
            # this is a normal disconnect, not a server exception.
            return
        except Exception as exc:
            if stream_started:
                try:
                    line = json.dumps({"type": "error", "error": str(exc)}, ensure_ascii=False) + "\n"
                    self.wfile.write(line.encode("utf-8"))
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, socket.timeout):
                    pass
            else:
                try:
                    self.send_json(400, {"error": str(exc)})
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, socket.timeout):
                    pass
        finally:
            if request_id:
                with _generation_events_lock:
                    _generation_cancel_events.pop(request_id, None)

    def log_message(self, fmt, *args):
        print("[web] " + fmt % args)


if __name__ == "__main__":
    port = int(os.environ.get("NIVESH_WEB_PORT", "8000"))
    address = ("127.0.0.1", port)
    print(f"Nivesh is running at http://127.0.0.1:{port}")
    print("Press Ctrl+C to stop the local server.")
    threading.Thread(target=preload_model, name="model-preload", daemon=True).start()
    try:
        ThreadingHTTPServer(address, Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nNivesh server stopped.")
    except OSError as exc:
        if getattr(exc, "winerror", None) == 10048 or getattr(exc, "errno", None) == 98:
            raise SystemExit("Port 8000 is already in use. Stop the older website window (Ctrl+C), then run python setup_and_run.py again.") from exc
        raise


