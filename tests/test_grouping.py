"""Tests for grouping.py — session grouping logic."""

import json
from unittest.mock import patch

import pytest

from src.constants import DEFAULT_GROUP_NAME
from src.grouping import _load_config, get_group_name


# ---------------------------------------------------------------------------
# _load_config (covers lines 38-43)
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def setup_method(self):
        # Reset the module-level cache before each test
        import src.grouping as _mod

        _mod._custom_config = None

    def test_returns_empty_dict_when_no_config_file(self, tmp_path):
        missing = str(tmp_path / "nonexistent.json")
        with patch("src.grouping.DASHBOARD_CONFIG_PATH", missing):
            result = _load_config()
        assert result == {}

    def test_loads_valid_config(self, tmp_path):
        config = {"grouping": {"mappings": {"myrepo": "My Project"}}}
        config_file = tmp_path / "dashboard-config.json"
        config_file.write_text(json.dumps(config))
        import src.grouping as _mod

        _mod._custom_config = None
        with patch("src.grouping.DASHBOARD_CONFIG_PATH", str(config_file)):
            result = _load_config()
        assert result == config

    def test_handles_malformed_json(self, tmp_path):
        config_file = tmp_path / "dashboard-config.json"
        config_file.write_text("not valid json {{{{")
        import src.grouping as _mod

        _mod._custom_config = None
        with patch("src.grouping.DASHBOARD_CONFIG_PATH", str(config_file)):
            result = _load_config()
        assert result == {}


# ---------------------------------------------------------------------------
# get_group_name (covers lines 69-71 — custom keyword mappings)
# ---------------------------------------------------------------------------


class TestGetGroupName:
    def setup_method(self):
        import src.grouping as _mod

        _mod._custom_config = None

    def test_custom_keyword_mapping(self, tmp_path):
        config = {"grouping": {"mappings": {"dashboard": "My Dashboard"}}}
        config_file = tmp_path / "dashboard-config.json"
        config_file.write_text(json.dumps(config))
        session = {"summary": "Working on the dashboard feature", "cwd": "/projects/app"}
        with patch("src.grouping.DASHBOARD_CONFIG_PATH", str(config_file)):
            result = get_group_name(session)
        assert result == "My Dashboard"

    def test_groups_by_repository_name(self, tmp_path):
        missing = str(tmp_path / "nonexistent.json")
        with patch("src.grouping.DASHBOARD_CONFIG_PATH", missing):
            session = {"repository": "owner/my-cool-repo", "cwd": "/projects/something"}
            result = get_group_name(session)
        assert result == "my-cool-repo"

    def test_groups_by_cwd_path(self, tmp_path):
        missing = str(tmp_path / "nonexistent.json")
        with patch("src.grouping.DASHBOARD_CONFIG_PATH", missing):
            session = {"cwd": "/Users/home/projects/my-project", "repository": ""}
            result = get_group_name(session)
        assert result == "my-project"

    def test_falls_back_to_default(self, tmp_path):
        missing = str(tmp_path / "nonexistent.json")
        with patch("src.grouping.DASHBOARD_CONFIG_PATH", missing):
            session = {"cwd": "", "repository": "", "summary": ""}
            result = get_group_name(session)
        assert result == DEFAULT_GROUP_NAME

    def test_empty_session_data(self, tmp_path):
        missing = str(tmp_path / "nonexistent.json")
        with patch("src.grouping.DASHBOARD_CONFIG_PATH", missing):
            result = get_group_name({})
        assert result == DEFAULT_GROUP_NAME

    def test_none_values_for_cwd_and_repository(self, tmp_path):
        missing = str(tmp_path / "nonexistent.json")
        with patch("src.grouping.DASHBOARD_CONFIG_PATH", missing):
            session = {"cwd": None, "repository": None, "summary": None}
            result = get_group_name(session)
        assert result == DEFAULT_GROUP_NAME
