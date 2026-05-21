import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from japanese_practice_mcp.paths import default_config_path, default_data_dir


@dataclass(frozen=True)
class Config:
    wanikani_token: str
    data_dir: Path
    subjects_max_age_days: int = 7
    assignments_ttl_seconds: int = 3600


def load_config(config_path: Path | None = None) -> Config:
    """Load config from TOML; env vars (JPMCP_*) override.

    Env vars:
      JPMCP_WANIKANI_TOKEN  -> wanikani_token
      JPMCP_DATA_DIR        -> data_dir
      JPMCP_CONFIG          -> path to config.toml (if config_path is None)
    """
    if config_path is None:
        env_path = os.environ.get("JPMCP_CONFIG")
        config_path = Path(env_path) if env_path else default_config_path()

    raw: dict = {}
    if config_path.exists():
        with config_path.open("rb") as f:
            raw = tomllib.load(f)

    token = os.environ.get("JPMCP_WANIKANI_TOKEN") or raw.get("wanikani_token")
    if not token:
        raise ValueError(
            f"wanikani_token not found. Set JPMCP_WANIKANI_TOKEN or add "
            f'`wanikani_token = "..."` to {config_path}.'
        )

    data_dir_str = os.environ.get("JPMCP_DATA_DIR") or raw.get("data_dir")
    data_dir = Path(data_dir_str) if data_dir_str else default_data_dir()

    return Config(
        wanikani_token=str(token),
        data_dir=data_dir,
        subjects_max_age_days=int(raw.get("subjects_max_age_days", 7)),
        assignments_ttl_seconds=int(raw.get("assignments_ttl_seconds", 3600)),
    )
