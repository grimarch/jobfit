"""Integration tests for CV generation API endpoints.

All Claude API calls and WeasyPrint rendering are mocked — no real LLM calls or
PDF rendering happen in CI. DB access uses the real test database.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from anthropic.types import TextBlock
from fastapi.testclient import TestClient

from jobfit.app import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _mock_claude_response(cv_dict: dict) -> MagicMock:
    block = MagicMock(spec=TextBlock)
    block.text = json.dumps(cv_dict)
    response = MagicMock()
    response.content = [block]
    return response


_FAKE_CV = {
    "language": "en",
    "name": "John Doe",
    "contact": {
        "city": "Berlin",
        "email": "john@doe.de",
        "phone": None,
        "linkedin": None,
        "github": "github.com/johndoe",
    },
    "summary": "Experienced DevOps engineer tailored for this role.",
    "experience": [
        {
            "title": "DevOps Engineer",
            "company": "Acme Corp",
            "location": "Berlin",
            "period": "01.2022 – present",
            "bullets": ["Built Kubernetes clusters", "Automated with Terraform"],
        }
    ],
    "skills": [{"category": "Cloud", "items": ["AWS", "GCP", "Terraform"]}],
    "education": [
        {
            "degree": "Bachelor",
            "institution": "Some University",
            "location": "Moscow",
            "period": "2011 – 2014",
        }
    ],
    "certifications": ["CKA"],
    "languages": [
        {"language": "English", "level": "C1"},
        {"language": "German", "level": "B2"},
    ],
    "tailoring_notes": ["Moved Kubernetes bullets to top for this role"],
}


# ── Helpers to get a real starred refnr ──────────────────────────────────────


def _get_starred_refnr() -> str | None:
    """Return the first starred refnr from the DB, or None if none exist."""
    from jobfit.db import get_session
    from jobfit.db.models import Classification as ClsModel

    with get_session() as session:
        row = (
            session.query(ClsModel.refnr)
            .filter(ClsModel.starred_at.isnot(None))
            .first()
        )
    return row[0] if row else None


def _get_any_refnr() -> str | None:
    """Return any refnr from the DB for negative tests."""
    from jobfit.db import get_session
    from jobfit.db.models import Classification as ClsModel

    with get_session() as session:
        row = session.query(ClsModel.refnr).first()
    return row[0] if row else None


# ── /api/cv/{refnr}/generate ──────────────────────────────────────────────────


def test_generate_cache_hit_returns_ready(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    refnr = _get_any_refnr()
    if refnr is None:
        pytest.skip("No classified jobs in test DB")

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    from jobfit.cv import generator as cv_generator

    path = cv_generator.output_path(refnr, "devops")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF fresh")
    try:
        resp = client.post(f"/api/cv/{refnr}/generate?role=devops")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert "url" in data
    finally:
        path.unlink(missing_ok=True)


def test_generate_cache_expired_returns_queued(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    refnr = _get_any_refnr()
    if refnr is None:
        pytest.skip("No classified jobs in test DB")

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    from jobfit.cv import generator as cv_generator

    path = cv_generator.output_path(refnr, "devops")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF stale")
    # Set mtime 25 hours in the past
    stale_mtime = path.stat().st_mtime - 25 * 3600
    import os

    os.utime(path, (stale_mtime, stale_mtime))
    try:
        with patch.object(cv_generator, "generate", return_value=b"%PDF fake"):
            resp = client.post(f"/api/cv/{refnr}/generate?role=devops")
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"
    finally:
        path.unlink(missing_ok=True)


def test_generate_returns_queued(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    refnr = _get_any_refnr()
    if refnr is None:
        pytest.skip("No classified jobs in test DB")

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    # BackgroundTask runs after response — patch generate to prevent real API call
    from jobfit.cv import generator as cv_generator

    with patch.object(cv_generator, "generate", return_value=b"%PDF fake"):
        resp = client.post(f"/api/cv/{refnr}/generate?role=devops")

    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"


def test_generate_status_ready_when_file_exists(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    refnr = _get_any_refnr()
    if refnr is None:
        pytest.skip("No classified jobs in test DB")

    from jobfit.cv import generator as cv_generator

    path = cv_generator.output_path(refnr, "devops")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF fake")

    try:
        resp = client.get(f"/api/cv/{refnr}/status?role=devops")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert "url" in data
    finally:
        path.unlink(missing_ok=True)


def test_generate_unknown_refnr_returns_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    resp = client.post("/api/cv/nonexistent-refnr-xyz-999/generate?role=devops")
    assert resp.status_code == 404


def _clear_cv_llm_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all env vars resolve_key(command_prefix='CV') can use."""
    for name in ("CV_API_KEY", "LLM_API_KEY", "CV_FALLBACK_API_KEY", "LLM_FALLBACK_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_generate_no_api_key_returns_400(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_cv_llm_api_keys(monkeypatch)
    refnr = _get_any_refnr() or "any-refnr"
    resp = client.post(f"/api/cv/{refnr}/generate?role=devops")
    assert resp.status_code == 400


# ── /api/cv/{refnr}/preview ───────────────────────────────────────────────────


def test_preview_returns_html(client: TestClient) -> None:
    refnr = _get_any_refnr()
    if refnr is None:
        pytest.skip("No classified jobs in test DB")

    from jobfit.cv import generator as cv_generator

    json_path = cv_generator.output_json_path(refnr, "devops")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(_FAKE_CV), encoding="utf-8")
    try:
        resp = client.get(f"/api/cv/{refnr}/preview?role=devops")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "John Doe" in resp.text
    finally:
        json_path.unlink(missing_ok=True)


def test_preview_html_contains_summary(client: TestClient) -> None:
    refnr = _get_any_refnr()
    if refnr is None:
        pytest.skip("No classified jobs in test DB")

    from jobfit.cv import generator as cv_generator

    json_path = cv_generator.output_json_path(refnr, "devops")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(_FAKE_CV), encoding="utf-8")
    try:
        resp = client.get(f"/api/cv/{refnr}/preview?role=devops")
        assert resp.status_code == 200
        assert "Experienced DevOps engineer" in resp.text
    finally:
        json_path.unlink(missing_ok=True)


def test_preview_unknown_refnr_returns_404(client: TestClient) -> None:
    resp = client.get("/api/cv/nonexistent-refnr-xyz-999/preview?role=devops")
    assert resp.status_code == 404


# ── GET /api/cv/{refnr}/download ──────────────────────────────────────────────


def test_cv_download_filename_matches_disk(client: TestClient) -> None:
    refnr = "test.refnr-special"
    from jobfit.cv import generator as cv_generator

    path = cv_generator.output_path(refnr, "devops")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF fake content")
    try:
        resp = client.get(f"/api/cv/{refnr}/download?role=devops")
        assert resp.status_code == 200
        assert f'filename="{path.name}"' in resp.headers["content-disposition"]
    finally:
        path.unlink(missing_ok=True)
