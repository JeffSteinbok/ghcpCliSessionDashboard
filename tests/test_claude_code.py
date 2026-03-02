"""Tests for the Claude Code session reader (src/claude_code.py)."""

import json
import os
from unittest.mock import patch

import pytest

from src.claude_code import (
    SESSION_ID_PREFIX,
    _build_restart_cmd,
    _extract_text,
    _extract_tool_uses,
    _find_transcript,
    get_claude_session_detail,
    get_claude_sessions,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def claude_projects(tmp_path):
    """Create a mock ~/.claude/projects directory with sessions."""
    projects_dir = tmp_path / "projects"
    project = projects_dir / "C--Users-test-myproject"
    project.mkdir(parents=True)

    # sessions-index.json
    index = {
        "version": 1,
        "entries": [
            {
                "sessionId": "aaaa-1111",
                "fullPath": str(project / "aaaa-1111.jsonl"),
                "firstPrompt": "Fix the login bug",
                "summary": "Login Bug Fix",
                "messageCount": 4,
                "created": "2026-02-01T10:00:00Z",
                "modified": "2026-02-01T11:00:00Z",
                "gitBranch": "fix/login",
                "projectPath": "C:\\Users\\test\\myproject",
                "isSidechain": False,
            },
            {
                "sessionId": "bbbb-2222",
                "fullPath": str(project / "bbbb-2222.jsonl"),
                "firstPrompt": "Add unit tests",
                "summary": "",
                "messageCount": 2,
                "created": "2026-02-02T14:00:00Z",
                "modified": "2026-02-02T15:00:00Z",
                "gitBranch": "",
                "projectPath": "C:\\Users\\test\\myproject",
                "isSidechain": False,
            },
        ],
        "originalPath": "C:\\Users\\test\\myproject",
    }
    (project / "sessions-index.json").write_text(json.dumps(index), encoding="utf-8")

    # Transcript for aaaa-1111
    transcript_lines = [
        json.dumps(
            {
                "type": "user",
                "sessionId": "aaaa-1111",
                "message": {"role": "user", "content": "Fix the login bug"},
                "uuid": "u1",
                "timestamp": "2026-02-01T10:00:00Z",
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "sessionId": "aaaa-1111",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "I'll fix that for you."},
                        {
                            "type": "tool_use",
                            "id": "t1",
                            "name": "Read",
                            "input": {"file_path": "src/auth.py"},
                        },
                    ],
                },
                "uuid": "a1",
                "timestamp": "2026-02-01T10:00:05Z",
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "sessionId": "aaaa-1111",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "t2",
                            "name": "Write",
                            "input": {"file_path": "src/auth.py", "content": "fixed"},
                        },
                    ],
                },
                "uuid": "a2",
                "timestamp": "2026-02-01T10:00:10Z",
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "sessionId": "aaaa-1111",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Done! The bug is fixed."}],
                },
                "uuid": "a3",
                "timestamp": "2026-02-01T10:00:15Z",
            }
        ),
    ]
    (project / "aaaa-1111.jsonl").write_text(
        "\n".join(transcript_lines), encoding="utf-8"
    )

    return str(projects_dir)


# ── get_claude_sessions ──────────────────────────────────────────────────────


class TestGetClaudeSessions:
    def test_returns_sessions_from_index(self, claude_projects):
        with patch("src.claude_code.CLAUDE_PROJECTS_DIR", claude_projects):
            sessions = get_claude_sessions()

        assert len(sessions) == 2

        s1 = next(s for s in sessions if s["id"] == f"{SESSION_ID_PREFIX}aaaa-1111")
        assert s1["summary"] == "Login Bug Fix"
        assert s1["branch"] == "fix/login"
        assert s1["turn_count"] == 4
        assert s1["source"] == "claude"
        assert s1["cwd"] == "C:\\Users\\test\\myproject"
        assert s1["created_at"] == "2026-02-01T10:00:00Z"

    def test_falls_back_to_first_prompt_for_summary(self, claude_projects):
        with patch("src.claude_code.CLAUDE_PROJECTS_DIR", claude_projects):
            sessions = get_claude_sessions()

        s2 = next(s for s in sessions if s["id"] == f"{SESSION_ID_PREFIX}bbbb-2222")
        assert s2["summary"] == "Add unit tests"

    def test_returns_empty_when_no_projects_dir(self, tmp_path):
        with patch("src.claude_code.CLAUDE_PROJECTS_DIR", str(tmp_path / "nope")):
            assert get_claude_sessions() == []

    def test_restart_cmd_format(self, claude_projects):
        with patch("src.claude_code.CLAUDE_PROJECTS_DIR", claude_projects):
            sessions = get_claude_sessions()

        s1 = next(s for s in sessions if s["id"] == f"{SESSION_ID_PREFIX}aaaa-1111")
        assert "claude --resume aaaa-1111" in s1["restart_cmd"]
        assert 'cd "C:\\Users\\test\\myproject"' in s1["restart_cmd"]

    def test_session_id_prefixed(self, claude_projects):
        with patch("src.claude_code.CLAUDE_PROJECTS_DIR", claude_projects):
            sessions = get_claude_sessions()

        for s in sessions:
            assert s["id"].startswith(SESSION_ID_PREFIX)


# ── get_claude_session_detail ────────────────────────────────────────────────


class TestGetClaudeSessionDetail:
    def test_parses_turns(self, claude_projects):
        with patch("src.claude_code.CLAUDE_PROJECTS_DIR", claude_projects):
            detail = get_claude_session_detail("aaaa-1111")

        turns = detail["turns"]
        assert len(turns) >= 2
        user_turns = [t for t in turns if t["user_message"]]
        assert user_turns[0]["user_message"] == "Fix the login bug"

    def test_parses_tool_counts(self, claude_projects):
        with patch("src.claude_code.CLAUDE_PROJECTS_DIR", claude_projects):
            detail = get_claude_session_detail("aaaa-1111")

        tool_counts = {tc["name"]: tc["count"] for tc in detail["tool_counts"]}
        assert tool_counts.get("Read") == 1
        assert tool_counts.get("Write") == 1

    def test_parses_files(self, claude_projects):
        with patch("src.claude_code.CLAUDE_PROJECTS_DIR", claude_projects):
            detail = get_claude_session_detail("aaaa-1111")

        assert "src/auth.py" in detail["files"]

    def test_unknown_session_returns_empty(self, claude_projects):
        with patch("src.claude_code.CLAUDE_PROJECTS_DIR", claude_projects):
            detail = get_claude_session_detail("nonexistent")

        assert detail["turns"] == []
        assert detail["tool_counts"] == []
        assert detail["files"] == []


# ── _extract_text ────────────────────────────────────────────────────────────


class TestExtractText:
    def test_string_content(self):
        assert _extract_text("Hello world") == "Hello world"

    def test_content_blocks(self):
        content = [
            {"type": "text", "text": "Part one."},
            {"type": "tool_use", "name": "Read", "input": {}},
            {"type": "text", "text": "Part two."},
        ]
        result = _extract_text(content)
        assert "Part one." in result
        assert "Part two." in result

    def test_meta_messages_skipped(self):
        assert _extract_text("<local-command-caveat>skip me</local-command-caveat>") == ""
        assert _extract_text("<command-name>/exit</command-name>") == ""


# ── _extract_tool_uses ───────────────────────────────────────────────────────


class TestExtractToolUses:
    def test_extracts_tool_names(self):
        content = [
            {"type": "tool_use", "name": "Read", "input": {}},
            {"type": "text", "text": "hi"},
            {"type": "tool_use", "name": "Write", "input": {}},
        ]
        assert _extract_tool_uses(content) == ["Read", "Write"]

    def test_returns_empty_for_string(self):
        assert _extract_tool_uses("some text") == []


# ── _build_restart_cmd ───────────────────────────────────────────────────────


class TestBuildRestartCmd:
    def test_with_cwd(self):
        cmd = _build_restart_cmd("abc-123", "/home/user/proj")
        assert cmd == 'cd "/home/user/proj" && claude --resume abc-123'

    def test_without_cwd(self):
        cmd = _build_restart_cmd("abc-123", "")
        assert cmd == "claude --resume abc-123"


# ── _find_transcript ─────────────────────────────────────────────────────────


class TestFindTranscript:
    def test_finds_existing_transcript(self, claude_projects):
        with patch("src.claude_code.CLAUDE_PROJECTS_DIR", claude_projects):
            path = _find_transcript("aaaa-1111")

        assert path is not None
        assert path.endswith("aaaa-1111.jsonl")

    def test_returns_none_for_missing(self, claude_projects):
        with patch("src.claude_code.CLAUDE_PROJECTS_DIR", claude_projects):
            assert _find_transcript("nonexistent") is None
