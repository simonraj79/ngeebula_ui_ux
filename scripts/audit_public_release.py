"""Inspect Git publication candidates without printing credential contents.

Run from any directory. This is a focused check, not a complete secret scanner.
Ignored files are never opened. Tracked private paths fail before content is read.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "Render API key": re.compile(r"\brnd_[A-Za-z0-9_-]{20,}"),
    "Google API key": re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    "GitHub access token": re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})"),
    "OpenAI-style key": re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{35,}"),
    "Private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "AWS access key ID": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
}


def private_path(name: str) -> bool:
    path = Path(name)
    base = path.name.lower()
    env_secret = (base == '.env' or base.startswith('.env.')) and not base.endswith('.example')
    return (env_secret or base == '.envrc' or base.startswith('secrets.') and not base.endswith('.example.toml')
            or base.endswith('.json') and base.startswith(('credentials', 'service-account', 'service_account'))
            or path.suffix.lower() in {'.db', '.sqlite', '.sqlite3', '.pem', '.key', '.pfx', '.p12', '.dpapi'}
            or any(marker in base for marker in ('.db-', '.sqlite-', '.sqlite3-'))
            or any(part in {'.run', '.venv', '.direnv', '__pycache__', '.pytest_cache', 'exports'} for part in path.parts)
            or name.replace('\\', '/').startswith('data/private/'))


def audit() -> int:
    result = subprocess.run(['git', '-C', str(ROOT), 'ls-files', '-co', '--exclude-standard', '-z'],
                            capture_output=True, check=True)
    names = sorted(set(result.stdout.decode('utf-8').split('\0')) - {''})
    findings = []
    for name in names:
        if private_path(name):
            findings.append(f'{name}: private/local path is a publication candidate')
            continue
        path = ROOT / name
        if path.is_symlink():
            findings.append(f'{name}: symbolic link requires review')
            continue
        if not path.is_file():
            continue
        if path.stat().st_size > 5_000_000:
            findings.append(f'{name}: file over 5 MB requires review')
            continue
        try:
            content = path.read_text(encoding='utf-8')
        except UnicodeError:
            continue
        for label, pattern in PATTERNS.items():
            for match in pattern.finditer(content):
                line = content.count('\n', 0, match.start()) + 1
                findings.append(f'{name}:{line}: possible {label} (value redacted)')
    print(f'Checked {len(names)} Git publication candidates; ignored files were not read.')
    for finding in findings:
        print(finding)
    print('PASS: no known-key patterns or private paths found.' if not findings else 'FAIL: resolve the findings before staging or publishing.')
    return bool(findings)


if __name__ == '__main__':
    raise SystemExit(audit())
