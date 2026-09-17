"""Start isolated Ngeebula capture services in hidden Windows processes."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / ".run"


def start(name: str, args: list[str], env: dict[str, str]) -> int:
    stdout = (RUN / f"video-{name}.stdout.log").open("ab")
    stderr = (RUN / f"video-{name}.stderr.log").open("ab")
    flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    process = subprocess.Popen(
        [sys.executable, *args], cwd=ROOT, env=env,
        stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
        creationflags=flags,
    )
    (RUN / f"video-{name}.pid").write_text(str(process.pid), encoding="ascii")
    return process.pid


def main() -> None:
    RUN.mkdir(exist_ok=True)
    (RUN / "video-localappdata").mkdir(exist_ok=True)
    env = os.environ.copy()
    env.update({
        "NGEEBULA_ENV_FILE": str(RUN / "video-empty.env"),
        "NGEEBULA_GEMINI_KEY_FILE": str(RUN / "video-empty-gemini.key"),
        "LOCALAPPDATA": str(RUN / "video-localappdata"),
    })
    backend_pid_file = RUN / "video-backend.pid"
    if not backend_pid_file.exists():
        backend_env = env | {"DATABASE_URL": "sqlite:///" + (RUN / "video-demo.sqlite3").as_posix()}
        print("backend", start("backend", ["-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8011"], backend_env))
    frontend_pid_file = RUN / "video-frontend.pid"
    if not frontend_pid_file.exists():
        frontend_env = env | {"NGEEBULA_API_URL": "http://127.0.0.1:8011"}
        print("frontend", start("frontend", ["-m", "streamlit", "run", "frontend/app.py", "--server.address", "127.0.0.1", "--server.port", "8511", "--server.headless", "true", "--browser.gatherUsageStats", "false"], frontend_env))


if __name__ == "__main__":
    main()
