"""Build the React frontend and install pinned Python runtime dependencies."""
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    npm = shutil.which('npm')
    if not npm:
        raise SystemExit('Node.js 22+ and npm are required to build the React frontend.')
    subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', 'requirements-lock.txt'], cwd=ROOT, check=True)
    subprocess.run([npm, 'ci'], cwd=ROOT / 'web', check=True)
    subprocess.run([npm, 'run', 'build'], cwd=ROOT / 'web', check=True)


if __name__ == '__main__':
    main()
