"""docs/BACKLOG.md and the GitHub Projects board must not drift apart.

The board is the status, the file is the why - which only works if the two agree
on what the items are. This test is that agreement, and it is allowed to skip
when gh is unavailable (offline, no auth) rather than fail for the wrong reason.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BACKLOG = ROOT / "docs" / "BACKLOG.md"
AGENTS = ROOT / "AGENTS.md"

PROJECT_NUMBER = "5"
PROJECT_OWNER = "roanh47"
HEADING_RE = re.compile(r"^##\s+\d+\s+—\s+(?P<title>.+?)\s*$", re.MULTILINE)


def backlog_titles() -> list[str]:
    return [m.group("title") for m in HEADING_RE.finditer(BACKLOG.read_text(encoding="utf-8"))]


def board_titles() -> list[str]:
    result = subprocess.run(
        ["gh", "project", "item-list", PROJECT_NUMBER, "--owner", PROJECT_OWNER,
         "--format", "json", "--limit", "200"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        pytest.skip(f"gh project item-list failed: {result.stderr.strip()[:200]}")
    items = json.loads(result.stdout).get("items", [])
    return [str((item.get("content") or {}).get("title") or "").strip() for item in items]


class TestBacklogFile:
    def test_the_file_lists_items(self):
        assert len(backlog_titles()) >= 5

    def test_every_item_gets_a_reason(self):
        text = BACKLOG.read_text(encoding="utf-8")
        sections = re.split(r"^##\s+\d+\s+—", text, flags=re.MULTILINE)[1:]
        for section in sections:
            body = section.strip()
            assert len(body) > 120, f"item has no real reason written down: {section[:40]!r}"

    def test_no_status_column_lives_here(self):
        text = BACKLOG.read_text(encoding="utf-8").lower()
        for banned in ("| status |", "status:", "- [x]", "- [ ]"):
            assert banned not in text, f"status belongs on the board, not in BACKLOG.md: {banned}"

    def test_points_at_the_board(self):
        assert f"projects/{PROJECT_NUMBER}" in BACKLOG.read_text(encoding="utf-8")


class TestAgentsContract:
    def test_agents_md_exists(self):
        assert AGENTS.is_file()

    def test_agents_md_points_at_the_board(self):
        text = AGENTS.read_text(encoding="utf-8")
        assert f"projects/{PROJECT_NUMBER}" in text
        assert "In progress" in text

    def test_agents_md_states_the_bind_rule(self):
        text = AGENTS.read_text(encoding="utf-8")
        assert "127.0.0.1" in text

    def test_agents_md_states_the_definition_of_done(self):
        text = AGENTS.read_text(encoding="utf-8").lower()
        assert "definition of done" in text


class TestBoardAgreement:
    def test_board_and_file_list_the_same_items(self):
        board = {title for title in board_titles() if title}
        backlog = set(backlog_titles())
        assert board, "the board has no items - is the project number right?"
        missing_from_file = board - backlog
        missing_from_board = backlog - board
        assert not missing_from_file, f"on the board, not in BACKLOG.md: {sorted(missing_from_file)}"
        assert not missing_from_board, f"in BACKLOG.md, not on the board: {sorted(missing_from_board)}"

    def test_gh_is_available_for_the_check_above(self):
        if shutil.which("gh") is None:
            pytest.skip("gh not installed")
        result = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, "gh is installed but not authenticated"
