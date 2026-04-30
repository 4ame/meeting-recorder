import json
import pytest
from pathlib import Path
from unittest.mock import patch
import config as cfg


def test_load_settings_returns_defaults_when_file_missing(tmp_path):
    with patch.object(cfg, "_CONFIG_FILE", tmp_path / "nonexistent.json"):
        result = cfg.load_settings()
    assert result == {"cr_enabled": False}


def test_load_settings_reads_existing_file(tmp_path):
    config_file = tmp_path / "settings.json"
    config_file.write_text('{"cr_enabled": true}', encoding="utf-8")
    with patch.object(cfg, "_CONFIG_FILE", config_file):
        result = cfg.load_settings()
    assert result["cr_enabled"] is True


def test_load_settings_returns_defaults_on_corrupt_json(tmp_path):
    config_file = tmp_path / "settings.json"
    config_file.write_text("not valid json", encoding="utf-8")
    with patch.object(cfg, "_CONFIG_FILE", config_file):
        result = cfg.load_settings()
    assert result == {"cr_enabled": False}


def test_save_settings_writes_file(tmp_path):
    config_file = tmp_path / "settings.json"
    with patch.object(cfg, "_CONFIG_FILE", config_file), \
         patch.object(cfg, "_CONFIG_DIR", tmp_path):
        cfg.save_settings({"cr_enabled": True})
    data = json.loads(config_file.read_text(encoding="utf-8"))
    assert data == {"cr_enabled": True}


def test_save_settings_creates_directory(tmp_path):
    config_dir = tmp_path / "subdir"
    config_file = config_dir / "settings.json"
    with patch.object(cfg, "_CONFIG_FILE", config_file), \
         patch.object(cfg, "_CONFIG_DIR", config_dir):
        cfg.save_settings({"cr_enabled": False})
    assert config_file.exists()
