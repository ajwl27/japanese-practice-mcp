from pathlib import Path

import platformdirs

APP_NAME = "japanese-practice-mcp"


def default_data_dir() -> Path:
    """Where the SQLite database lives.

    Linux:   ~/.local/share/japanese-practice-mcp
    macOS:   ~/Library/Application Support/japanese-practice-mcp
    Windows: %LOCALAPPDATA%\\japanese-practice-mcp
    """
    return Path(platformdirs.user_data_dir(APP_NAME, appauthor=False))


def default_config_dir() -> Path:
    """Where config.toml lives.

    Linux:   ~/.config/japanese-practice-mcp
    macOS:   ~/Library/Application Support/japanese-practice-mcp
    Windows: %APPDATA%\\japanese-practice-mcp
    """
    return Path(platformdirs.user_config_dir(APP_NAME, appauthor=False, roaming=True))


def default_config_path() -> Path:
    return default_config_dir() / "config.toml"
