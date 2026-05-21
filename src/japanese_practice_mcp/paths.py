from pathlib import Path

import platformdirs

APP_NAME = "japanese-practice-mcp"


def default_data_dir() -> Path:
    return Path(platformdirs.user_data_dir(APP_NAME))


def default_config_dir() -> Path:
    return Path(platformdirs.user_config_dir(APP_NAME))


def default_config_path() -> Path:
    return default_config_dir() / "config.toml"
