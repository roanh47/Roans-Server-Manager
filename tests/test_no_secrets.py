"""No secret ever lands in the repository.

This panel is public on GitHub, and it holds a token that unlocks a shell on a
server. The check runs over the tracked files, not the working tree, because
that is what gets published.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

SECRET_PATTERNS = {
    "github token": r"gh[pousr]_[A-Za-z0-9]{20,}",
    "openai-style key": r"sk-[A-Za-z0-9]{20,}",
    "alpaca key": r"APCA[A-Z0-9]{10,}",
    "private key block": r"BEGIN (RSA|OPENSSH|EC|PGP) PRIVATE KEY",
    "assigned SM_TOKEN": r'SM_TOKEN\s*=\s*["\']?[A-Za-z0-9_\-]{12,}',
    "bearer literal": r"Bearer\s+[A-Za-z0-9_\-\.]{25,}",
}

ALLOWED = (
    ".env.example",  # documents the variable, carries no value
    "tests/test_no_secrets.py",
)


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        pytest.skip("not a git repository")
    return [ROOT / line for line in result.stdout.splitlines() if line.strip()]


def test_there_are_tracked_files():
    if not tracked_files():
        pytest.skip("nothing committed yet")


def test_no_secret_pattern_in_tracked_files():
    hits: list[str] = []
    for path in tracked_files():
        if path.name in ALLOWED or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if re.search(pattern, text):
                hits.append(f"{path.relative_to(ROOT)}: {label}")
    assert not hits, "possible secrets in tracked files: " + ", ".join(hits)


def test_env_is_not_tracked():
    tracked = {str(p.relative_to(ROOT)) for p in tracked_files()}
    assert ".env" not in tracked


def test_env_is_gitignored():
    assert ".env" in (ROOT / ".gitignore").read_text(encoding="utf-8")
