"""Tests for build_restart_command and _extract_extra_args."""

import sys
import os
import importlib

# Import the module in a way that handles relative imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.dashboard_app import _extract_extra_args, build_restart_command


class TestExtractExtraArgs:
    def test_empty(self):
        assert _extract_extra_args("") == ""
        assert _extract_extra_args(None) == ""

    def test_yolo_only(self):
        assert _extract_extra_args("copilot --resume abc123 --yolo") == "--yolo"

    def test_model_flag(self):
        result = _extract_extra_args("copilot --resume abc123 --yolo --model gpt-4")
        assert "--model" in result and "gpt-4" in result
        assert "--yolo" in result

    def test_resume_stripped(self):
        result = _extract_extra_args("copilot --resume abc123 --yolo")
        assert "--resume" not in result
        assert "abc123" not in result

    def test_node_prefix(self):
        result = _extract_extra_args("node /usr/bin/copilot --resume sid --yolo")
        assert result == "--yolo"

    def test_no_extra_args(self):
        assert _extract_extra_args("copilot --resume abc123") == ""


class TestBuildRestartCommand:
    def test_basic(self):
        session = {"id": "abc123", "cwd": ""}
        cmd = build_restart_command(session)
        assert cmd == "copilot --resume abc123"

    def test_with_cwd(self):
        session = {"id": "abc123", "cwd": "/home/user/project"}
        cmd = build_restart_command(session)
        assert 'cd "/home/user/project"' in cmd
        assert "copilot --resume abc123" in cmd

    def test_yolo_flag(self):
        session = {"id": "abc123", "cwd": ""}
        cmd = build_restart_command(session, yolo=True)
        assert "--yolo" in cmd

    def test_cmdline_extra_args_override_yolo(self):
        session = {"id": "abc123", "cwd": ""}
        cmd = build_restart_command(
            session, yolo=False, cmdline="copilot --resume abc123 --yolo --model gpt-4"
        )
        assert "--yolo" in cmd
        assert "--model gpt-4" in cmd

    def test_cmdline_empty_falls_back_to_yolo(self):
        session = {"id": "abc123", "cwd": ""}
        cmd = build_restart_command(session, yolo=True, cmdline="")
        assert "--yolo" in cmd

    def test_windows_path_in_cwd(self):
        session = {"id": "abc123", "cwd": r"C:\Users\me\project"}
        cmd = build_restart_command(session)
        assert r'cd "C:\Users\me\project"' in cmd
