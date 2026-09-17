"""Start the React/FastAPI service as one signal-aware process on Render."""
from __future__ import annotations

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    if not (ROOT / 'web' / 'dist' / 'index.html').is_file():
        print('React build missing. Run python scripts/build_render.py before starting.', flush=True)
        return 1
    port = os.environ.get('PORT', '10000')
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        print('PORT must be an integer between 1 and 65535.', flush=True)
        return 1
    os.chdir(ROOT)
    env = dict(os.environ, NGEEBULA_HOSTED='1')
    command = [sys.executable, '-m', 'uvicorn', 'backend.main:app',
               '--host', '0.0.0.0', '--port', port, '--workers', '1']
    os.execvpe(sys.executable, command, env)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
