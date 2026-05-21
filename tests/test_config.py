from pathlib import Path

import pytest

from japanese_practice_mcp.config import load_config


def write_toml(p: Path, content: str) -> None:
    p.write_text(content, encoding="utf-8")


def test_loads_from_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_file = tmp_path / "config.toml"
    write_toml(cfg_file, 'wanikani_token = "wk-from-file"\ndata_dir = "/tmp/x"\n')
    monkeypatch.delenv("JPMCP_WANIKANI_TOKEN", raising=False)
    monkeypatch.delenv("JPMCP_DATA_DIR", raising=False)
    cfg = load_config(config_path=cfg_file)
    assert cfg.wanikani_token == "wk-from-file"
    assert cfg.data_dir == Path("/tmp/x")


def test_env_overrides_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_file = tmp_path / "config.toml"
    write_toml(cfg_file, 'wanikani_token = "wk-from-file"\n')
    monkeypatch.setenv("JPMCP_WANIKANI_TOKEN", "wk-from-env")
    cfg = load_config(config_path=cfg_file)
    assert cfg.wanikani_token == "wk-from-env"


def test_missing_token_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_file = tmp_path / "config.toml"
    write_toml(cfg_file, "")
    monkeypatch.delenv("JPMCP_WANIKANI_TOKEN", raising=False)
    with pytest.raises(ValueError, match="wanikani_token"):
        load_config(config_path=cfg_file)


def test_no_config_file_with_env_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JPMCP_WANIKANI_TOKEN", "wk-from-env")
    monkeypatch.setenv("JPMCP_DATA_DIR", str(tmp_path / "d"))
    cfg = load_config(config_path=tmp_path / "nonexistent.toml")
    assert cfg.wanikani_token == "wk-from-env"
    assert cfg.data_dir == tmp_path / "d"
