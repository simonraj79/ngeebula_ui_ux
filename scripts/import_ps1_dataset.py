"""Reproduce or verify the byte-identical pinned PS1 public dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import urllib.request
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DESTINATION = REPO_ROOT / "data" / "ps1"


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, help="Local upstream PS1 directory; otherwise download pinned raw files")
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    manifest_path = DEFAULT_DESTINATION / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    destination = args.destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    base_url = (
        "https://raw.githubusercontent.com/aochinwen/"
        f"NebulaX-Hackathon-ProblemStatement/{manifest['source_commit']}/PS1"
    )
    for relative, expected in manifest["files"].items():
        output = destination / Path(relative)
        if args.verify_only:
            if not output.is_file():
                raise SystemExit(f"missing pinned file: {relative}")
            payload = output.read_bytes()
        elif args.source:
            source = args.source.resolve() / Path(relative)
            if not source.is_file():
                raise SystemExit(f"missing source file: {relative}")
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, output)
            payload = output.read_bytes()
        else:
            with urllib.request.urlopen(f"{base_url}/{relative}", timeout=30) as response:
                payload = response.read()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(payload)
        if len(payload) != expected["bytes"] or digest(payload) != expected["sha256"]:
            raise SystemExit(f"hash or size mismatch: {relative}")
    print(f"Verified {len(manifest['files'])} pinned PS1 files at {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
