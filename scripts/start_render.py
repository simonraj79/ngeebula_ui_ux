"""Run the public Streamlit demo with a supervised, loopback-only API."""
from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    env = os.environ.copy()
    env.update(NGEEBULA_HOSTED="1", NGEEBULA_API_URL="http://127.0.0.1:8000")
    children = []
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        api = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"],
            cwd=ROOT, env=env,
        )
        children.append(api)
        ready = False
        for _ in range(120):
            if stopping or api.poll() is not None:
                break
            try:
                with urlopen(env["NGEEBULA_API_URL"] + "/openapi.json", timeout=1) as response:
                    ready = response.status == 200
                if ready:
                    break
            except (URLError, TimeoutError):
                time.sleep(0.5)
        if not ready:
            print("Internal API did not become ready.", flush=True)
            return 0 if stopping else 1
        ui = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", "app.py", "--server.address", "0.0.0.0",
             "--server.port", env.get("PORT", "10000"), "--server.headless", "true",
             "--browser.gatherUsageStats", "false"], cwd=ROOT / "frontend", env=env,
        )
        children.append(ui)
        while not stopping:
            if any(child.poll() is not None for child in children):
                print("A required application process exited; restarting the service is required.", flush=True)
                return 1
            time.sleep(0.5)
        return 0
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
        for child in reversed(children):
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
