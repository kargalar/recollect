import tempfile
from pathlib import Path

import config
import main


def run():
    original_config_file = config.CONFIG_FILE
    try:
        with tempfile.TemporaryDirectory() as directory:
            config.CONFIG_FILE = Path(directory) / "config.json"
            assert config.save_config({
                "images_path": "images",
                "screenshot_interval": 10,
                "auto_pause_on_idle": True,
                "is_paused": True,
            })
            loaded = config.load_config()
            assert loaded["is_paused"] is True
            assert loaded["screenshot_interval"] == 10

        assert main.period_start("all", main.STATS_RANGES) is None
        try:
            main.period_start("invalid", main.STATS_RANGES)
        except Exception as error:
            assert error.status_code == 400
        else:
            raise AssertionError("invalid range accepted")
    finally:
        config.CONFIG_FILE = original_config_file


if __name__ == "__main__":
    run()
    print("self-check: OK")
