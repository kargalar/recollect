import json
import os
import sys
from pathlib import Path

BASE_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
CONFIG_FILE = BASE_DIR / "config.json"
DEFAULT_CONFIG = {
    "images_path": "images",
    "screenshot_interval": 60,
    "auto_pause_on_idle": True,
    "is_paused": False
}

MIN_SCREENSHOT_INTERVAL = 1
MAX_SCREENSHOT_INTERVAL = 3600


def _normalise_config(config):
    merged = DEFAULT_CONFIG.copy()
    if isinstance(config, dict):
        merged.update(config)

    if not isinstance(merged.get("images_path"), str) or not merged["images_path"].strip():
        merged["images_path"] = DEFAULT_CONFIG["images_path"]

    interval = merged.get("screenshot_interval")
    if (
        isinstance(interval, bool)
        or not isinstance(interval, int)
        or not MIN_SCREENSHOT_INTERVAL <= interval <= MAX_SCREENSHOT_INTERVAL
    ):
        merged["screenshot_interval"] = DEFAULT_CONFIG["screenshot_interval"]

    for key in ("auto_pause_on_idle", "is_paused"):
        if not isinstance(merged.get(key), bool):
            merged[key] = DEFAULT_CONFIG[key]

    return merged


def load_config():
    if not CONFIG_FILE.exists():
        config = DEFAULT_CONFIG.copy()
        save_config(config)
        return config
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as file:
            return _normalise_config(json.load(file))
    except Exception as e:
        print(f"Error loading config: {e}")
        return DEFAULT_CONFIG.copy()

def save_config(config):
    config = _normalise_config(config)
    temporary_file = CONFIG_FILE.with_suffix(".tmp")
    try:
        with temporary_file.open("w", encoding="utf-8") as file:
            json.dump(config, file, indent=4)
        os.replace(temporary_file, CONFIG_FILE)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        try:
            temporary_file.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def get_images_path(config=None):
    config = config or load_config()
    path = Path(config.get("images_path", DEFAULT_CONFIG["images_path"])).expanduser()
    return path if path.is_absolute() else BASE_DIR / path
