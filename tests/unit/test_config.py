"""Tests for jobfit.config path resolution."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def _reload_config() -> object:
    from jobfit import config

    return importlib.reload(config)


def _clear_all(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("JOBFIT_DATA_DIR", "JOBFIT_JOBS_DATA_DIR", "JOBFIT_USER_DATA_DIR"):
        monkeypatch.delenv(var, raising=False)


def test_default_data_dir_is_cwd_data(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _clear_all(monkeypatch)
    monkeypatch.chdir(tmp_path)
    config = _reload_config()
    assert config.DATA_DIR == tmp_path / "data"
    assert config.JOBS_DATA_DIR == tmp_path / "data" / "jobs"
    assert config.USER_DATA_DIR == tmp_path / "data" / "user"
    assert config.role_input_dir("devops") == tmp_path / "data" / "user" / "devops" / "input"
    assert config.role_output_dir("devops") == tmp_path / "data" / "user" / "devops" / "output"


def test_data_dir_from_env_absolute(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _clear_all(monkeypatch)
    monkeypatch.setenv("JOBFIT_DATA_DIR", str(tmp_path))
    config = _reload_config()
    assert config.DATA_DIR == tmp_path
    assert config.JOBS_DATA_DIR == tmp_path / "jobs"
    assert config.USER_DATA_DIR == tmp_path / "user"


def test_data_dir_from_env_tilde(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _clear_all(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path.parent))
    monkeypatch.setenv("JOBFIT_DATA_DIR", f"~/{tmp_path.name}")
    config = _reload_config()
    assert config.DATA_DIR == tmp_path


def test_data_dir_from_env_relative(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _clear_all(monkeypatch)
    rel = Path("custom-data")
    monkeypatch.setenv("JOBFIT_DATA_DIR", str(rel))
    monkeypatch.chdir(tmp_path)
    config = _reload_config()
    assert config.DATA_DIR == tmp_path / rel


def test_jobs_data_dir_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _clear_all(monkeypatch)
    jobs_dir = tmp_path / "jobs-override"
    monkeypatch.setenv("JOBFIT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JOBFIT_JOBS_DATA_DIR", str(jobs_dir))
    config = _reload_config()
    assert config.JOBS_DATA_DIR == jobs_dir
    assert config.RAW_DIR == jobs_dir / "raw"
    assert config.USER_DATA_DIR == tmp_path / "user"


def test_user_data_dir_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _clear_all(monkeypatch)
    user_dir = tmp_path / "user-override"
    monkeypatch.setenv("JOBFIT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JOBFIT_USER_DATA_DIR", str(user_dir))
    config = _reload_config()
    assert config.USER_DATA_DIR == user_dir
    assert config.role_input_dir("devops") == user_dir / "devops" / "input"
    assert config.role_output_dir("devops") == user_dir / "devops" / "output"
    assert config.JOBS_DATA_DIR == tmp_path / "jobs"


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
