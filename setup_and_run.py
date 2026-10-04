"""Start Nivesh and begin loading its AI models in the background."""
from pathlib import Path
import os
import socket
import subprocess
import sys
import time
import webbrowser
import json
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parent
PREFERRED_PORTS = (8000, 8002, 8003, 8004, 8080, 8081, 8888)


def choose_web_port():
    """Use 8000 when free, or select another local port if a static server owns it."""
    for port in PREFERRED_PORTS:
        if port == 8001:  # reserved for the Fraud Checker API
            continue
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind(("127.0.0.1", port))
            return port
        except OSError:
            continue
        finally:
            probe.close()
    raise SystemExit("No available website port was found. Close an older website server and run setup_and_run.py again.")


def main():
    port = choose_web_port()
    url = f"http://127.0.0.1:{port}/"
    environment = os.environ.copy()
    environment["NIVESH_WEB_PORT"] = str(port)
    print(f"Starting Nivesh on {url}", flush=True)
    if port != 8000:
        print("Port 8000 is serving another app, so Nivesh is using this available port instead.", flush=True)
    print("The fraud checker, vision, chat, and available speech models begin loading in the background.")
    process = subprocess.Popen([sys.executable, str(ROOT / "web_app.py")], cwd=str(ROOT), env=environment)
    deadline = time.monotonic() + 30
    ready = False
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise SystemExit(f"Nivesh stopped during startup (exit code {process.returncode}).")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                print("Website server is responding; opening the English dashboard.", flush=True)
                ready = True
                break
        except OSError:
            time.sleep(0.25)
    if not ready:
        print("The local readiness check was blocked; opening the site URL anyway. Keep this terminal window open.", flush=True)
    active_server_path = ROOT / "nivesh-active-server.json"
    if ready:
        # Older website processes serve workspace files statically. Publishing
        # this address lets those tabs redirect to the current website run.
        active_server_tmp = active_server_path.with_suffix(".json.tmp")
        active_server_tmp.write_text(json.dumps({
            "url": url,
            "port": port,
            "pid": process.pid,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }), encoding="utf-8")
        active_server_tmp.replace(active_server_path)
        print(f"CURRENT WEBSITE URL (use this exact address): {url}", flush=True)
        print("An older tab in this project will redirect here when you reload it.", flush=True)
    webbrowser.open(url)
    try:
        process.wait()
    except KeyboardInterrupt:
        process.terminate()
        process.wait()
    finally:
        # Do not leave an address that points to a stopped website run.
        try:
            active = json.loads(active_server_path.read_text(encoding="utf-8"))
            if active.get("pid") == process.pid:
                active_server_path.unlink(missing_ok=True)
        except (OSError, ValueError, json.JSONDecodeError):
            pass


if __name__ == "__main__":
    main()
