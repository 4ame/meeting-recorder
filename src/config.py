import json
from pathlib import Path

_CONFIG_DIR = Path.home() / ".meeting_recorder"
_CONFIG_FILE = _CONFIG_DIR / "settings.json"
_DEFAULTS: dict = {"cr_enabled": False}


def load_settings() -> dict:
    try:
        with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {**_DEFAULTS, **data}
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(_DEFAULTS)


def save_settings(data: dict) -> None:
    try:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError as e:
        print(f"[config] Erreur écriture settings : {e}")
