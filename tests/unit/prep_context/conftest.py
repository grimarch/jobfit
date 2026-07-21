"""Prep-context tests run without host user input files (claims_layout.yaml, gap_lines.yaml)."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_user_input_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point role_input_dir at an empty per-test tree (no host JOBFIT_USER_DATA_DIR)."""
    user_root = tmp_path / "user"

    def _role_input_dir(role_slug: str = "devops") -> Path:
        path = user_root / role_slug / "input"
        path.mkdir(parents=True, exist_ok=True)
        return path

    monkeypatch.setattr("jobfit.config.role_input_dir", _role_input_dir)
