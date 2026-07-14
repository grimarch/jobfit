"""Integration tests for Anschreiben generation API endpoints.

All LLM calls and WeasyPrint rendering are mocked — no real API calls happen in CI.
DB access uses the real test database.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from jobfit.app import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _get_any_refnr() -> str | None:
    """Return any refnr from the DB for use in tests."""
    from jobfit.db import get_session
    from jobfit.db.models import Classification as ClsModel

    with get_session() as session:
        row = session.query(ClsModel.refnr).first()
    return row[0] if row else None


# ── POST /api/anschreiben/{refnr}/generate ────────────────────────────────────

def test_anschreiben_generate_queues(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    refnr = _get_any_refnr()
    if refnr is None:
        pytest.skip("No classified jobs in test DB")

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    from jobfit.anschreiben import generator as anschreiben_generator

    with patch.object(anschreiben_generator, "generate", return_value=b"%PDF fake"):
        resp = client.post(f"/api/anschreiben/{refnr}/generate?role=devops")

    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"


def test_anschreiben_generate_returns_ready_if_exists(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    refnr = _get_any_refnr()
    if refnr is None:
        pytest.skip("No classified jobs in test DB")

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    from jobfit.anschreiben import generator as anschreiben_generator

    path = anschreiben_generator.output_path(refnr, "devops")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF fresh")
    try:
        resp = client.post(f"/api/anschreiben/{refnr}/generate?role=devops")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert "url" in data
    finally:
        path.unlink(missing_ok=True)


def _clear_cv_llm_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all env vars resolve_key(command_prefix='CV') can use."""
    for name in ("CV_API_KEY", "LLM_API_KEY", "CV_FALLBACK_API_KEY", "LLM_FALLBACK_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_anschreiben_generate_no_api_key_returns_400(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_cv_llm_api_keys(monkeypatch)
    refnr = _get_any_refnr() or "any-refnr"
    resp = client.post(f"/api/anschreiben/{refnr}/generate?role=devops")
    assert resp.status_code == 400


def test_anschreiben_generate_unknown_refnr_returns_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    resp = client.post("/api/anschreiben/nonexistent-refnr-zzz-999/generate?role=devops")
    assert resp.status_code == 404


# ── GET /api/anschreiben/{refnr}/status ──────────────────────────────────────

def test_anschreiben_status_generating(client: TestClient) -> None:
    refnr = "status-test-refnr"
    role = "devops"

    from jobfit.app import _GENERATING_ANSCHREIBEN, _FAILED_ANSCHREIBEN

    _GENERATING_ANSCHREIBEN.add((refnr, role))
    _FAILED_ANSCHREIBEN.discard((refnr, role))
    try:
        resp = client.get(f"/api/anschreiben/{refnr}/status?role={role}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "generating"
    finally:
        _GENERATING_ANSCHREIBEN.discard((refnr, role))


def test_anschreiben_status_ready_when_file_exists(client: TestClient) -> None:
    refnr = _get_any_refnr()
    if refnr is None:
        pytest.skip("No classified jobs in test DB")

    from jobfit.anschreiben import generator as anschreiben_generator

    path = anschreiben_generator.output_path(refnr, "devops")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF fake")
    try:
        resp = client.get(f"/api/anschreiben/{refnr}/status?role=devops")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert "url" in data
    finally:
        path.unlink(missing_ok=True)


def test_anschreiben_status_failed(client: TestClient) -> None:
    refnr = "failed-test-refnr"
    role = "devops"

    from jobfit.app import _GENERATING_ANSCHREIBEN, _FAILED_ANSCHREIBEN

    _FAILED_ANSCHREIBEN.add((refnr, role))
    _GENERATING_ANSCHREIBEN.discard((refnr, role))
    try:
        resp = client.get(f"/api/anschreiben/{refnr}/status?role={role}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "failed"
    finally:
        _FAILED_ANSCHREIBEN.discard((refnr, role))


# ── GET /api/anschreiben/{refnr}/download ────────────────────────────────────

def test_anschreiben_download_not_found(client: TestClient) -> None:
    resp = client.get("/api/anschreiben/nonexistent-refnr-zzz-999/download?role=devops")
    assert resp.status_code == 404


def test_anschreiben_download_serves_pdf(client: TestClient) -> None:
    refnr = _get_any_refnr()
    if refnr is None:
        pytest.skip("No classified jobs in test DB")

    from jobfit.anschreiben import generator as anschreiben_generator

    path = anschreiben_generator.output_path(refnr, "devops")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF fake content")
    try:
        resp = client.get(f"/api/anschreiben/{refnr}/download?role=devops")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert b"%PDF fake content" in resp.content
    finally:
        path.unlink(missing_ok=True)


# ── GET /api/anschreiben/{refnr}/preview ─────────────────────────────────────

def test_anschreiben_preview_not_found(client: TestClient) -> None:
    resp = client.get("/api/anschreiben/nonexistent-refnr-zzz-999/preview?role=devops")
    assert resp.status_code == 404


def test_anschreiben_preview_returns_html(client: TestClient) -> None:
    import json
    refnr = "preview-test-refnr"
    from jobfit.anschreiben import generator as anschreiben_generator

    fake_letter = {
        "language": "de", "candidate_name": "Test User",
        "contact": {"city": "Berlin", "email": "test@example.com", "phone": None,
                    "linkedin": None, "xing": None, "github": None},
        "date": "11. Juli 2026", "firma": "Acme GmbH",
        "subject": "Bewerbung als DevOps Engineer",
        "salutation": "Sehr geehrte Damen und Herren,",
        "body_paragraphs": ["Einleitung.", "Hauptteil.", "Schluss."],
        "closing": "Mit freundlichen Grüßen",
        "gehaltsvorstellung": None, "starttermin": None, "tailoring_notes": [],
    }
    json_path = anschreiben_generator.output_json_path(refnr, "devops")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(fake_letter), encoding="utf-8")
    try:
        with patch("jobfit.anschreiben.generator.render._render_html", return_value="<html>preview</html>"):
            resp = client.get(f"/api/anschreiben/{refnr}/preview?role=devops")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
    finally:
        json_path.unlink(missing_ok=True)


def test_anschreiben_download_filename_matches_disk(client: TestClient) -> None:
    refnr = "test.refnr-special"
    from jobfit.anschreiben import generator as anschreiben_generator

    path = anschreiben_generator.output_path(refnr, "devops")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF fake content")
    try:
        resp = client.get(f"/api/anschreiben/{refnr}/download?role=devops")
        assert resp.status_code == 200
        assert f'filename="{path.name}"' in resp.headers["content-disposition"]
    finally:
        path.unlink(missing_ok=True)
