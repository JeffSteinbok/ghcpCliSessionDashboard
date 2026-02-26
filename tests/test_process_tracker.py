"""Tests for process_tracker.py — event parsing and session state detection."""

import json
import os
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from src.process_tracker import (
    _event_data_cache,
    _get_session_state,
    _match_process_to_session,
    _parse_iso_timestamp,
    _parse_mcp_servers,
    _read_event_data,
    _read_recent_events,
    get_recent_output,
    get_session_event_data,
)

EVENTS_DIR = os.path.join(os.path.expanduser("~"), ".copilot", "session-state")


# ---------------------------------------------------------------------------
# _parse_iso_timestamp
# ---------------------------------------------------------------------------


class TestParseIsoTimestamp:
    def test_valid_iso_string(self):
        ts = "2026-01-15T10:30:00+00:00"
        result = _parse_iso_timestamp(ts)
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 15

    def test_z_suffix(self):
        ts = "2026-01-15T10:30:00Z"
        result = _parse_iso_timestamp(ts)
        assert result.year == 2026

    def test_invalid_raises(self):
        with pytest.raises((ValueError, AttributeError)):
            _parse_iso_timestamp("not-a-timestamp")


# ---------------------------------------------------------------------------
# _parse_mcp_servers
# ---------------------------------------------------------------------------


class TestParseMcpServers:
    def test_no_flag_returns_empty(self):
        assert _parse_mcp_servers("copilot --resume abc-123") == []

    def test_missing_file_returns_empty(self, tmp_path):
        config_path = str(tmp_path / "nonexistent.json")
        cmdline = f"copilot --additional-mcp-config {config_path}"
        assert _parse_mcp_servers(cmdline) == []

    def test_valid_config_returns_server_names(self, tmp_path):
        config = {"mcpServers": {"github": {}, "slack": {}}}
        config_file = tmp_path / "mcp.json"
        config_file.write_text(json.dumps(config))
        cmdline = f"copilot --additional-mcp-config {config_file}"
        result = _parse_mcp_servers(cmdline)
        assert set(result) == {"github", "slack"}

    def test_empty_mcp_servers_returns_empty(self, tmp_path):
        config = {"mcpServers": {}}
        config_file = tmp_path / "mcp.json"
        config_file.write_text(json.dumps(config))
        cmdline = f"copilot --additional-mcp-config {config_file}"
        assert _parse_mcp_servers(cmdline) == []

    def test_malformed_json_returns_empty(self, tmp_path):
        config_file = tmp_path / "mcp.json"
        config_file.write_text("not valid json")
        cmdline = f"copilot --additional-mcp-config {config_file}"
        assert _parse_mcp_servers(cmdline) == []


# ---------------------------------------------------------------------------
# _read_recent_events
# ---------------------------------------------------------------------------


class TestReadRecentEvents:
    def test_missing_file_returns_empty(self, tmp_path):
        with patch("src.process_tracker.EVENTS_DIR", str(tmp_path)):
            result = _read_recent_events("nonexistent-session")
        assert result == []

    def test_reads_last_n_events(self, tmp_path, make_events):
        events = [{"type": f"event.{i}", "data": {}} for i in range(20)]
        make_events("sess-1", events)
        with patch("src.process_tracker.EVENTS_DIR", str(tmp_path)):
            result = _read_recent_events("sess-1", count=5)
        assert len(result) == 5
        assert result[-1]["type"] == "event.19"

    def test_skips_malformed_lines(self, tmp_path):
        session_dir = tmp_path / "sess-bad"
        session_dir.mkdir()
        events_file = session_dir / "events.jsonl"
        events_file.write_text('{"type": "good"}\nnot json\n{"type": "also good"}\n')
        with patch("src.process_tracker.EVENTS_DIR", str(tmp_path)):
            result = _read_recent_events("sess-bad", count=10)
        assert len(result) == 2
        assert all("type" in e for e in result)

    def test_empty_file_returns_empty(self, tmp_path):
        session_dir = tmp_path / "sess-empty"
        session_dir.mkdir()
        (session_dir / "events.jsonl").write_text("")
        with patch("src.process_tracker.EVENTS_DIR", str(tmp_path)):
            result = _read_recent_events("sess-empty")
        assert result == []


# ---------------------------------------------------------------------------
# _get_session_state
# ---------------------------------------------------------------------------


class TestGetSessionState:
    def _write_events(self, tmp_path, session_id, events):
        session_dir = tmp_path / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        events_file = session_dir / "events.jsonl"
        with open(events_file, "w") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")

    def test_no_events_returns_unknown(self, tmp_path):
        with patch("src.process_tracker.EVENTS_DIR", str(tmp_path)):
            result = _get_session_state("nonexistent")
        assert result["state"] == "unknown"

    def test_ask_user_tool_returns_waiting(self, tmp_path):
        events = [
            {
                "type": "tool.execution_start",
                "data": {
                    "toolCallId": "tc1",
                    "toolName": "ask_user",
                    "arguments": {"question": "What should I do?", "choices": ["A", "B"]},
                },
            }
        ]
        self._write_events(tmp_path, "sess-1", events)
        with patch("src.process_tracker.EVENTS_DIR", str(tmp_path)):
            result = _get_session_state("sess-1")
        assert result["state"] == "waiting"
        assert "What should I do?" in result["waiting_context"]
        assert "A" in result["waiting_context"]

    def test_pending_tool_returns_working(self, tmp_path):
        events = [
            {
                "type": "tool.execution_start",
                "data": {"toolCallId": "tc1", "toolName": "view", "arguments": {}},
            }
        ]
        self._write_events(tmp_path, "sess-1", events)
        with patch("src.process_tracker.EVENTS_DIR", str(tmp_path)):
            result = _get_session_state("sess-1")
        assert result["state"] == "working"

    def test_completed_tool_returns_idle(self, tmp_path):
        events = [
            {
                "type": "tool.execution_start",
                "data": {"toolCallId": "tc1", "toolName": "view", "arguments": {}},
            },
            {
                "type": "tool.execution_complete",
                "data": {"toolCallId": "tc1"},
            },
            {"type": "assistant.turn_end", "data": {}},
        ]
        self._write_events(tmp_path, "sess-1", events)
        with patch("src.process_tracker.EVENTS_DIR", str(tmp_path)):
            result = _get_session_state("sess-1")
        assert result["state"] == "idle"

    def test_user_message_returns_thinking(self, tmp_path):
        events = [{"type": "user.message", "data": {"message": "do something"}}]
        self._write_events(tmp_path, "sess-1", events)
        with patch("src.process_tracker.EVENTS_DIR", str(tmp_path)):
            result = _get_session_state("sess-1")
        assert result["state"] == "thinking"

    def test_subagent_started_returns_working(self, tmp_path):
        events = [{"type": "subagent.started", "data": {}}]
        self._write_events(tmp_path, "sess-1", events)
        with patch("src.process_tracker.EVENTS_DIR", str(tmp_path)):
            result = _get_session_state("sess-1")
        assert result["state"] == "working"

    def test_stale_pending_tool_returns_waiting(self, tmp_path):
        old_time = (datetime.now(UTC) - timedelta(seconds=120)).isoformat()
        events = [
            {
                "type": "tool.execution_start",
                "timestamp": old_time,
                "data": {"toolCallId": "tc1", "toolName": "view", "arguments": {}},
            }
        ]
        self._write_events(tmp_path, "sess-1", events)
        with patch("src.process_tracker.EVENTS_DIR", str(tmp_path)):
            result = _get_session_state("sess-1")
        assert result["state"] == "waiting"


# ---------------------------------------------------------------------------
# _match_process_to_session
# ---------------------------------------------------------------------------


class TestMatchProcessToSession:
    def _write_session_start(self, tmp_path, session_id, timestamp):
        session_dir = tmp_path / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        event = {"type": "session.start", "timestamp": timestamp, "data": {}}
        (session_dir / "events.jsonl").write_text(json.dumps(event) + "\n")

    def test_matches_within_tolerance(self, tmp_path):
        ts = datetime.now(UTC)
        self._write_session_start(tmp_path, "sess-match", ts.isoformat())
        # Process created 3 seconds before the session.start event
        proc_ts = (ts - timedelta(seconds=3)).isoformat()
        with patch("src.process_tracker.EVENTS_DIR", str(tmp_path)):
            result = _match_process_to_session(proc_ts)
        assert result == "sess-match"

    def test_no_match_beyond_tolerance(self, tmp_path):
        ts = datetime.now(UTC)
        self._write_session_start(tmp_path, "sess-far", ts.isoformat())
        # Process created 30 seconds away — beyond 10s window
        proc_ts = (ts - timedelta(seconds=30)).isoformat()
        with patch("src.process_tracker.EVENTS_DIR", str(tmp_path)):
            result = _match_process_to_session(proc_ts)
        assert result is None

    def test_invalid_creation_date_returns_none(self, tmp_path):
        with patch("src.process_tracker.EVENTS_DIR", str(tmp_path)):
            result = _match_process_to_session("not-a-date")
        assert result is None


# ---------------------------------------------------------------------------
# _read_event_data
# ---------------------------------------------------------------------------


class TestReadEventData:
    def _write_events(self, tmp_path, session_id, events):
        session_dir = tmp_path / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        with open(session_dir / "events.jsonl", "w") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")

    def test_missing_file_returns_defaults(self, tmp_path):
        with patch("src.process_tracker.EVENTS_DIR", str(tmp_path)):
            data = _read_event_data("nonexistent")
        assert data.tool_calls == 0
        assert data.mcp_servers == []
        assert data.intent == ""

    def test_reads_session_context(self, tmp_path):
        events = [
            {
                "type": "session.start",
                "data": {
                    "context": {
                        "cwd": "/project",
                        "branch": "main",
                        "repository": "owner/repo",
                    }
                },
            }
        ]
        self._write_events(tmp_path, "sess-1", events)
        with patch("src.process_tracker.EVENTS_DIR", str(tmp_path)):
            data = _read_event_data("sess-1")
        assert data.cwd == "/project"
        assert data.branch == "main"
        assert data.repository == "owner/repo"

    def test_counts_tool_calls(self, tmp_path):
        events = [
            {"type": "tool.execution_complete", "data": {}},
            {"type": "tool.execution_complete", "data": {}},
            {"type": "tool.execution_complete", "data": {}},
        ]
        self._write_events(tmp_path, "sess-1", events)
        with patch("src.process_tracker.EVENTS_DIR", str(tmp_path)):
            data = _read_event_data("sess-1")
        assert data.tool_calls == 3

    def test_reads_intent(self, tmp_path):
        events = [
            {
                "type": "tool.execution_start",
                "data": {
                    "toolName": "report_intent",
                    "arguments": {"intent": "Fixing the bug"},
                },
            }
        ]
        self._write_events(tmp_path, "sess-1", events)
        with patch("src.process_tracker.EVENTS_DIR", str(tmp_path)):
            data = _read_event_data("sess-1")
        assert data.intent == "Fixing the bug"

    def test_reads_mcp_servers_from_info_event(self, tmp_path):
        events = [
            {
                "type": "info",
                "data": {
                    "infoType": "mcp",
                    "message": "Configured MCP servers: github, slack",
                },
            }
        ]
        self._write_events(tmp_path, "sess-1", events)
        with patch("src.process_tracker.EVENTS_DIR", str(tmp_path)):
            data = _read_event_data("sess-1")
        assert "github" in data.mcp_servers
        assert "slack" in data.mcp_servers


# ---------------------------------------------------------------------------
# get_session_event_data (caching)
# ---------------------------------------------------------------------------


class TestGetSessionEventData:
    def test_inactive_session_is_cached(self, tmp_path):
        _event_data_cache.clear()
        session_dir = tmp_path / "sess-cache"
        session_dir.mkdir()
        (session_dir / "events.jsonl").write_text("")

        with patch("src.process_tracker.EVENTS_DIR", str(tmp_path)):
            result1 = get_session_event_data("sess-cache", is_running=False)
            result2 = get_session_event_data("sess-cache", is_running=False)

        assert result1 is result2  # same object from cache

    def test_active_session_not_cached(self, tmp_path):
        _event_data_cache.clear()
        session_dir = tmp_path / "sess-active"
        session_dir.mkdir()
        (session_dir / "events.jsonl").write_text("")

        with patch("src.process_tracker.EVENTS_DIR", str(tmp_path)):
            result1 = get_session_event_data("sess-active", is_running=True)
            result2 = get_session_event_data("sess-active", is_running=True)

        # Active sessions are re-read each time, not the same cached object
        assert "sess-active" not in _event_data_cache


# ---------------------------------------------------------------------------
# get_recent_output
# ---------------------------------------------------------------------------


class TestGetRecentOutput:
    def test_missing_file_returns_empty(self, tmp_path):
        with patch("src.process_tracker.EVENTS_DIR", str(tmp_path)):
            result = get_recent_output("nonexistent")
        assert result == []

    def test_returns_last_tool_output(self, tmp_path):
        session_dir = tmp_path / "sess-1"
        session_dir.mkdir()
        events = [
            {
                "type": "tool.execution_complete",
                "data": {"result": {"content": "line1\nline2\nline3"}},
            }
        ]
        with open(session_dir / "events.jsonl", "w") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")
        with patch("src.process_tracker.EVENTS_DIR", str(tmp_path)):
            result = get_recent_output("sess-1", max_lines=10)
        assert "line1" in result

    def test_skips_intent_logged_content(self, tmp_path):
        session_dir = tmp_path / "sess-1"
        session_dir.mkdir()
        events = [
            {
                "type": "tool.execution_complete",
                "data": {"result": {"content": "Intent logged"}},
            }
        ]
        with open(session_dir / "events.jsonl", "w") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")
        with patch("src.process_tracker.EVENTS_DIR", str(tmp_path)):
            result = get_recent_output("sess-1")
        assert result == []
