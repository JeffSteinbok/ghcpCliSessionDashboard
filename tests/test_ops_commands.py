"""Tests for autostart and upgrade refresh-message CLI commands."""

import argparse
import sys
from unittest.mock import MagicMock, call, patch

import pytest

from src.session_dashboard import (
    TASK_NAME,
    _get_autostart_cmd_str,
    cmd_autostart,
    cmd_autostart_remove,
    cmd_upgrade,
)


# ---------------------------------------------------------------------------
# _get_autostart_cmd_str
# ---------------------------------------------------------------------------


class TestGetAutostartCmdStr:
    def test_uses_copilot_dashboard_when_found(self):
        with patch("shutil.which", return_value="C:\\copilot-dashboard.exe"):
            result = _get_autostart_cmd_str(5111)
        assert result == '"C:\\copilot-dashboard.exe" start --background --port 5111'

    def test_falls_back_to_python_module(self):
        with patch("shutil.which", return_value=None):
            result = _get_autostart_cmd_str(8080)
        assert sys.executable in result
        assert "8080" in result
        assert "-m src.session_dashboard" in result


# ---------------------------------------------------------------------------
# cmd_autostart — platform gate + registry
# ---------------------------------------------------------------------------


class TestCmdAutostart:
    def test_errors_on_non_windows(self):
        args = argparse.Namespace(port=5111)
        with patch("src.session_dashboard.sys") as mock_sys:
            mock_sys.platform = "darwin"
            mock_sys.exit = MagicMock(side_effect=SystemExit(1))
            with pytest.raises(SystemExit):
                cmd_autostart(args)

    @patch("src.session_dashboard.sys")
    @patch("shutil.which", return_value="C:\\copilot-dashboard.exe")
    def test_writes_registry_on_windows(self, _which, mock_sys):
        mock_sys.platform = "win32"
        mock_sys.exit = sys.exit
        mock_sys.executable = sys.executable
        mock_winreg = MagicMock()
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__ = MagicMock(return_value=mock_key)
        mock_winreg.OpenKey.return_value.__exit__ = MagicMock(return_value=False)
        mock_winreg.HKEY_CURRENT_USER = 0x80000001
        mock_winreg.KEY_SET_VALUE = 0x0002
        mock_winreg.REG_SZ = 1
        args = argparse.Namespace(port=5111)
        with patch.dict("sys.modules", {"winreg": mock_winreg}):
            cmd_autostart(args)
        mock_winreg.SetValueEx.assert_called_once()
        set_call = mock_winreg.SetValueEx.call_args
        assert set_call[0][0] == mock_key
        assert set_call[0][1] == TASK_NAME

    @patch("src.session_dashboard.sys")
    @patch("shutil.which", return_value="C:\\copilot-dashboard.exe")
    def test_fails_gracefully(self, _which, mock_sys):
        mock_sys.platform = "win32"
        mock_sys.exit = MagicMock(side_effect=SystemExit(1))
        mock_sys.executable = sys.executable
        mock_winreg = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__ = MagicMock()
        mock_winreg.OpenKey.return_value.__exit__ = MagicMock(return_value=False)
        mock_winreg.HKEY_CURRENT_USER = 0x80000001
        mock_winreg.KEY_SET_VALUE = 0x0002
        mock_winreg.REG_SZ = 1
        mock_winreg.SetValueEx.side_effect = OSError("Permission denied")
        args = argparse.Namespace(port=5111)
        with patch.dict("sys.modules", {"winreg": mock_winreg}):
            with pytest.raises(SystemExit):
                cmd_autostart(args)


# ---------------------------------------------------------------------------
# cmd_autostart_remove — platform gate + registry
# ---------------------------------------------------------------------------


class TestCmdAutostartRemove:
    def test_errors_on_non_windows(self):
        args = argparse.Namespace()
        with patch("src.session_dashboard.sys") as mock_sys:
            mock_sys.platform = "linux"
            mock_sys.exit = MagicMock(side_effect=SystemExit(1))
            with pytest.raises(SystemExit):
                cmd_autostart_remove(args)

    @patch("src.session_dashboard.sys")
    def test_deletes_registry_value_on_windows(self, mock_sys):
        mock_sys.platform = "win32"
        mock_sys.exit = sys.exit
        mock_winreg = MagicMock()
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__ = MagicMock(return_value=mock_key)
        mock_winreg.OpenKey.return_value.__exit__ = MagicMock(return_value=False)
        mock_winreg.HKEY_CURRENT_USER = 0x80000001
        mock_winreg.KEY_SET_VALUE = 0x0002
        with patch.dict("sys.modules", {"winreg": mock_winreg}):
            cmd_autostart_remove(argparse.Namespace())
        mock_winreg.DeleteValue.assert_called_once_with(mock_key, TASK_NAME)

    @patch("src.session_dashboard.sys")
    def test_handles_not_found(self, mock_sys, capsys):
        mock_sys.platform = "win32"
        mock_sys.exit = sys.exit
        mock_winreg = MagicMock()
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__ = MagicMock(return_value=mock_key)
        mock_winreg.OpenKey.return_value.__exit__ = MagicMock(return_value=False)
        mock_winreg.HKEY_CURRENT_USER = 0x80000001
        mock_winreg.KEY_SET_VALUE = 0x0002
        mock_winreg.DeleteValue.side_effect = FileNotFoundError
        with patch.dict("sys.modules", {"winreg": mock_winreg}):
            cmd_autostart_remove(argparse.Namespace())
        out = capsys.readouterr().out
        assert "not currently configured" in out


# ---------------------------------------------------------------------------
# cmd_upgrade — refresh message
# ---------------------------------------------------------------------------


class TestUpgradeRefreshMessage:
    @patch("src.session_dashboard.subprocess.Popen")
    @patch("shutil.which", return_value="copilot-dashboard")
    @patch("src.session_dashboard.subprocess.run")
    @patch("src.session_dashboard._read_pid_file", return_value=12345)
    @patch("os.kill")
    @patch("os.path.exists", return_value=True)
    @patch("os.remove")
    def test_prints_refresh_message(
        self, _rm, _exists, _kill, _read_pid, mock_run, _which, _popen, capsys
    ):
        # pip upgrade succeeds
        mock_run.side_effect = [
            MagicMock(returncode=0),  # taskkill / stop
            MagicMock(returncode=0),  # pip install
            MagicMock(returncode=0, stdout="0.8.0\n"),  # version check
        ]
        cmd_upgrade(argparse.Namespace())
        out = capsys.readouterr().out
        assert "refresh your browser" in out.lower()


# ---------------------------------------------------------------------------
# API: /api/autostart endpoints
# ---------------------------------------------------------------------------


class TestApiAutostartStatus:
    @patch("src.dashboard_api.sys")
    def test_supported_and_enabled(self, mock_sys, client):
        mock_sys.platform = "win32"
        mock_winreg = MagicMock()
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__ = MagicMock(return_value=mock_key)
        mock_winreg.OpenKey.return_value.__exit__ = MagicMock(return_value=False)
        mock_winreg.HKEY_CURRENT_USER = 0x80000001
        mock_winreg.KEY_READ = 0x20019
        with patch.dict("sys.modules", {"winreg": mock_winreg}):
            resp = client.get("/api/autostart")
        assert resp.status_code == 200
        data = resp.json()
        assert data["supported"] is True
        assert data["enabled"] is True

    @patch("src.dashboard_api.sys")
    def test_supported_but_not_enabled(self, mock_sys, client):
        mock_sys.platform = "win32"
        mock_winreg = MagicMock()
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__ = MagicMock(return_value=mock_key)
        mock_winreg.OpenKey.return_value.__exit__ = MagicMock(return_value=False)
        mock_winreg.HKEY_CURRENT_USER = 0x80000001
        mock_winreg.KEY_READ = 0x20019
        mock_winreg.QueryValueEx.side_effect = FileNotFoundError
        with patch.dict("sys.modules", {"winreg": mock_winreg}):
            resp = client.get("/api/autostart")
        data = resp.json()
        assert data["supported"] is True
        assert data["enabled"] is False

    @patch("src.dashboard_api.sys")
    def test_not_supported_on_mac(self, mock_sys, client):
        mock_sys.platform = "darwin"
        resp = client.get("/api/autostart")
        data = resp.json()
        assert data["supported"] is False
        assert data["enabled"] is False


class TestApiAutostartEnable:
    @patch("src.dashboard_api.sys")
    def test_fails_on_non_windows(self, mock_sys, client):
        mock_sys.platform = "linux"
        resp = client.post("/api/autostart/enable")
        data = resp.json()
        assert data["success"] is False

    @patch("src.dashboard_api.sys")
    def test_success_on_windows(self, mock_sys, client):
        mock_sys.platform = "win32"
        mock_sys.executable = sys.executable
        mock_winreg = MagicMock()
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__ = MagicMock(return_value=mock_key)
        mock_winreg.OpenKey.return_value.__exit__ = MagicMock(return_value=False)
        mock_winreg.HKEY_CURRENT_USER = 0x80000001
        mock_winreg.KEY_SET_VALUE = 0x0002
        mock_winreg.REG_SZ = 1
        with patch.dict("sys.modules", {"winreg": mock_winreg}):
            with patch("shutil.which", return_value="C:\\copilot-dashboard.exe"):
                resp = client.post("/api/autostart/enable")
        data = resp.json()
        assert data["success"] is True

    @patch("src.dashboard_api.sys")
    def test_failure_on_windows(self, mock_sys, client):
        mock_sys.platform = "win32"
        mock_sys.executable = sys.executable
        mock_winreg = MagicMock()
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__ = MagicMock(return_value=mock_key)
        mock_winreg.OpenKey.return_value.__exit__ = MagicMock(return_value=False)
        mock_winreg.HKEY_CURRENT_USER = 0x80000001
        mock_winreg.KEY_SET_VALUE = 0x0002
        mock_winreg.REG_SZ = 1
        mock_winreg.SetValueEx.side_effect = OSError("Access denied")
        with patch.dict("sys.modules", {"winreg": mock_winreg}):
            with patch("shutil.which", return_value="C:\\copilot-dashboard.exe"):
                resp = client.post("/api/autostart/enable")
        data = resp.json()
        assert data["success"] is False
        assert "Access denied" in data["message"]
