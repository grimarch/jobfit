"""Tests for jobfit.config path resolution."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def _reload_config() -> object:
    from jobfit import config

    return importlib.reload(config)


def test_default_data_dir_uses_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JOBFIT_DATA_DIR", raising=False)
    config = _reload_config()
    assert config.DATA_DIR == Path.home() / "Projects" / "secrets" / "jobfit" / "data"
    assert config.role_input_dir("devops") == config.DATA_DIR / "devops" / "input"
    assert config.role_output_dir("devops") == config.DATA_DIR / "devops" / "output"


def test_data_dir_from_env_absolute(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("JOBFIT_DATA_DIR", str(tmp_path))
    config = _reload_config()
    assert config.DATA_DIR == tmp_path


def test_data_dir_from_env_tilde(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path.parent))
    monkeypatch.setenv("JOBFIT_DATA_DIR", f"~/{tmp_path.name}")
    config = _reload_config()
    assert config.DATA_DIR == tmp_path


def test_data_dir_from_env_relative(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    rel = Path("custom-data")
    monkeypatch.setenv("JOBFIT_DATA_DIR", str(rel))
    monkeypatch.chdir(tmp_path)
    config = _reload_config()
    assert config.DATA_DIR == tmp_path / rel


def test_log_data_dir_logs_once(monkeypatch: pytest.MonkeyPatch) -> None:
    import jobfit.config as config

    config._data_dir_logged = False
    calls: list[tuple[Path, Path]] = []

    def _fake_log(data_dir: Path, role_input: Path) -> None:
        calls.append((data_dir, role_input))

    monkeypatch.setattr(config, "_log_data_dir", _fake_log)

    config.log_data_dir()
    config.log_data_dir()

    assert len(calls) == 1
    assert calls[0] == (
        config.DATA_DIR.resolve(),
        config.role_input_dir("devops").resolve(),
    )
