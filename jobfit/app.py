"""FastAPI application for the JobFit dashboard."""

import asyncio
import hashlib
import json
import time
from asyncio import create_task
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, override
from urllib.parse import quote

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request

from jobfit.cache import (
    build_all,
    render_cv,
    render_listings,
    render_skills,
    render_targets,
)
from jobfit.config import REPORTS_DIR, log_data_dir, log_reports_dir
from jobfit.db import get_session
from jobfit.db.models import Classification as ClsModel
from jobfit.db.models import Job as JobModel
from jobfit.roles import DEFAULT_ROLE
from jobfit.startup import check_startup

# ── App lifecycle ─────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(_app: FastAPI):
    FastAPICache.init(InMemoryBackend())
    log_data_dir()
    log_reports_dir()
    check_startup(DEFAULT_ROLE)
    await build_all()
    logger.info("Dashboards ready — http://127.0.0.1:8888")
    yield


app = FastAPI(title="JobFit", lifespan=lifespan)


# ── ETag middleware ───────────────────────────────────────────────────────────


class _ETagMiddleware(BaseHTTPMiddleware):
    """Add ETag + Cache-Control to HTML responses; return 304 on match."""

    @override
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        if (
            request.method == "GET"
            and response.status_code == 200
            and "text/html" in response.headers.get("content-type", "")
        ):
            body = b"".join([chunk async for chunk in response.body_iterator])  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType, reportAttributeAccessIssue]
            etag = f'"{hashlib.md5(body).hexdigest()}"'
            if request.headers.get("if-none-match") == etag:
                return Response(status_code=304, headers={"ETag": etag})
            headers = {
                **dict(response.headers),
                "ETag": etag,
                "Cache-Control": "no-cache",
            }
            return Response(
                content=body,
                status_code=200,
                headers=headers,
                media_type=response.media_type,
            )
        return response


app.add_middleware(_ETagMiddleware)


# ── Static ────────────────────────────────────────────────────────────────────


@app.get("/plotly.min.js", include_in_schema=False)
def plotly_js() -> FileResponse:
    path = REPORTS_DIR / "plotly.min.js"
    if not path.exists():
        raise HTTPException(status_code=404, detail="plotly.min.js not found")
    return FileResponse(path, media_type="application/javascript")


# ── Dashboard routes ──────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse, response_model=None)
async def dashboard_targets(role: str = DEFAULT_ROLE) -> str | Response:
    return await render_targets(role)


@app.get("/listings", response_class=HTMLResponse, response_model=None)
async def dashboard_listings(role: str = DEFAULT_ROLE) -> str | Response:
    return await render_listings(role)


@app.get("/cv", response_class=HTMLResponse, response_model=None)
async def dashboard_cv(role: str = DEFAULT_ROLE) -> str | Response:
    return await render_cv(role)


@app.get("/skills", response_class=HTMLResponse, response_model=None)
async def dashboard_skills(role: str = DEFAULT_ROLE) -> str | Response:
    return await render_skills(role)


# ── Read / Unread ─────────────────────────────────────────────────────────────


@app.post("/api/read/{refnr}")
def mark_read(refnr: str) -> dict[str, Any]:
    with get_session() as session:
        cls = session.get(ClsModel, refnr)
        if cls is None:
            raise HTTPException(status_code=404, detail="Job not found")
        cls.read_at = datetime.now(timezone.utc)
    return {"ok": True, "refnr": refnr}


@app.delete("/api/read/{refnr}")
def mark_unread(refnr: str) -> dict[str, Any]:
    with get_session() as session:
        cls = session.get(ClsModel, refnr)
        if cls is None:
            raise HTTPException(status_code=404, detail="Job not found")
        cls.read_at = None
    return {"ok": True, "refnr": refnr}


@app.get("/api/read-status")
def read_status(role: str = DEFAULT_ROLE) -> dict[str, Any]:
    """Return refnrs of read jobs (read_at IS NOT NULL) for the given role."""
    with get_session() as session:
        rows = (
            session.query(ClsModel.refnr)
            .join(JobModel, ClsModel.refnr == JobModel.refnr)
            .filter(
                ClsModel.role == role,
                JobModel.closed_at.is_(None),
                ClsModel.read_at.isnot(None),
            )
            .all()
        )
        return {"read": [r[0] for r in rows]}


# ── Starred / Unstarred ───────────────────────────────────────────────────────


@app.post("/api/starred/{refnr}")
def mark_starred(refnr: str) -> dict[str, Any]:
    with get_session() as session:
        cls = session.get(ClsModel, refnr)
        if cls is None:
            raise HTTPException(status_code=404, detail="Job not found")
        cls.starred_at = datetime.now(timezone.utc)
    return {"ok": True, "refnr": refnr}


@app.delete("/api/starred/{refnr}")
def mark_unstarred(refnr: str) -> dict[str, Any]:
    with get_session() as session:
        cls = session.get(ClsModel, refnr)
        if cls is None:
            raise HTTPException(status_code=404, detail="Job not found")
        cls.starred_at = None
    return {"ok": True, "refnr": refnr}


@app.get("/api/starred-status")
def starred_status(role: str = DEFAULT_ROLE) -> dict[str, Any]:
    """Return refnrs of starred jobs (starred_at IS NOT NULL) for the given role."""
    with get_session() as session:
        rows = (
            session.query(ClsModel.refnr)
            .join(JobModel, ClsModel.refnr == JobModel.refnr)
            .filter(
                ClsModel.role == role,
                JobModel.closed_at.is_(None),
                ClsModel.starred_at.isnot(None),
            )
            .all()
        )
        return {"starred": [r[0] for r in rows]}


# ── Jobs API ──────────────────────────────────────────────────────────────────


@app.get("/api/jobs")
def api_jobs(role: str = DEFAULT_ROLE) -> list[dict[str, Any]]:
    with get_session() as session:
        rows = (
            session.query(ClsModel, JobModel)
            .join(JobModel, ClsModel.refnr == JobModel.refnr)
            .filter(ClsModel.role == role, JobModel.closed_at.is_(None))
            .all()
        )
        return [
            {
                "refnr": job.refnr,
                "firma": cls.firma,
                "titel": cls.titel,
                "work_mode": cls.work_mode,
                "company_stage": cls.company_stage,
                "industry": cls.industry,
                "read_at": cls.read_at.isoformat() if cls.read_at else None,
            }
            for cls, job in rows
        ]


# ── CV generation ─────────────────────────────────────────────────────────────


# Track which (refnr, role) pairs are currently being generated or have failed
_GENERATING: set[tuple[str, str]] = set()
_FAILED: set[tuple[str, str]] = set()


def _archive_cv(refnr: str, role: str) -> None:
    import shutil

    from jobfit.cv import generator as cv_generator

    pdf = cv_generator.output_path(refnr, role)
    json_path = cv_generator.output_json_path(refnr, role)
    candidates = [p for p in (pdf, json_path) if p.exists()]
    if not candidates:
        return
    history_dir = pdf.parent / "history"
    history_dir.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    for path in candidates:
        shutil.move(str(path), str(history_dir / f"{path.stem}_{ts}{path.suffix}"))


async def _cv_generate_bg(refnr: str, role: str, api_key: str) -> None:
    from jobfit.cv import generator as cv_generator

    _archive_cv(refnr, role)
    try:
        await asyncio.to_thread(cv_generator.generate, refnr, role, api_key)
        _FAILED.discard((refnr, role))
    except Exception as exc:
        logger.error(f"Background CV generation failed for {refnr!r}: {exc}")
        _FAILED.add((refnr, role))
    finally:
        _GENERATING.discard((refnr, role))


@app.post("/api/cv/{refnr}/generate")
async def api_cv_generate(
    refnr: str, background_tasks: BackgroundTasks, role: str = DEFAULT_ROLE
) -> JSONResponse:
    """Queue CV generation as a background task; return immediately."""
    from jobfit.llm import resolve_key

    try:
        api_key = resolve_key(command_prefix="CV")
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    with get_session() as session:
        if session.get(JobModel, refnr) is None:
            raise HTTPException(status_code=404, detail=f"Job not found: {refnr}")

    from jobfit.cv import generator as cv_generator

    path = cv_generator.output_path(refnr, role)
    if path.exists() and (time.time() - path.stat().st_mtime) < 86400:
        url = f"/api/cv/{quote(refnr, safe='')}/download?role={quote(role, safe='')}"
        return JSONResponse({"status": "ready", "url": url})

    _GENERATING.add((refnr, role))
    _FAILED.discard((refnr, role))
    background_tasks.add_task(_cv_generate_bg, refnr, role, api_key)
    return JSONResponse({"status": "queued"})


@app.get("/api/cv/{refnr}/status")
def api_cv_status(refnr: str, role: str = DEFAULT_ROLE) -> JSONResponse:
    """Check whether a generated CV PDF is ready for download."""
    from jobfit.cv import generator as cv_generator

    if (refnr, role) in _GENERATING:
        return JSONResponse({"status": "generating"})

    if (refnr, role) in _FAILED:
        return JSONResponse({"status": "failed"})

    path = cv_generator.output_path(refnr, role)
    if path.exists():
        url = f"/api/cv/{quote(refnr, safe='')}/download?role={quote(role, safe='')}"
        return JSONResponse({"status": "ready", "url": url})
    return JSONResponse({"status": "generating"})


@app.get("/api/cv/{refnr}/download")
def api_cv_download(refnr: str, role: str = DEFAULT_ROLE) -> Response:
    """Serve a previously generated CV PDF from disk."""
    from jobfit.cv import generator as cv_generator

    path = cv_generator.output_path(refnr, role)
    if not path.exists():
        raise HTTPException(
            status_code=404, detail="CV not yet generated for this vacancy"
        )

    return Response(
        content=path.read_bytes(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{path.name}"'},
    )


@app.get("/api/cv/{refnr}/preview")
def api_cv_preview(refnr: str, role: str = DEFAULT_ROLE) -> HTMLResponse:
    """Render saved CV JSON as HTML with ATS report (no API call)."""
    from jobfit import ats_validator
    from jobfit.cv import generator as cv_generator
    from jobfit.roles import ROLES

    json_path = cv_generator.output_json_path(refnr, role)
    if not json_path.exists():
        raise HTTPException(
            status_code=404,
            detail="CV not yet generated for this vacancy. Use POST /api/cv/{refnr}/generate first.",
        )

    cv_data = json.loads(json_path.read_text(encoding="utf-8"))

    photo_b64 = cv_generator._load_photo(role)
    ats_report = None
    pdf_path = cv_generator.output_path(refnr, role)
    role_obj = ROLES.get(role)
    if pdf_path.exists() and role_obj is not None:
        try:
            job_ctx = cv_generator._load_job_context(refnr, role)
            ats_report = ats_validator.validate(
                pdf_path, cv_data, job_ctx["beschreibung"], role_obj.skills,
                has_photo=photo_b64 is not None,
            )
        except Exception as exc:
            logger.warning(f"ATS validation skipped: {exc}")
    return HTMLResponse(
        content=cv_generator._render_html(
            cv_data,
            ats_report=ats_report,
            photo_b64=photo_b64,
            refnr=refnr,
            role=role,
        )
    )


@app.post("/api/cv/{refnr}/archive")
def api_cv_archive(refnr: str, role: str = DEFAULT_ROLE) -> JSONResponse:
    """Move current CV PDF + JSON to history/ with UTC timestamp."""
    _archive_cv(refnr, role)
    return JSONResponse({"status": "archived"})


@app.put("/api/cv/{refnr}/json")
async def api_cv_save_json(refnr: str, request: Request, role: str = DEFAULT_ROLE) -> JSONResponse:
    """Save edited CV JSON and re-render PDF (no LLM call)."""
    from jobfit.cv import generator as cv_generator

    body = await request.body()
    try:
        cv_data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")

    json_path = cv_generator.output_json_path(refnr, role)
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="CV not found. Generate first.")

    json_path.write_text(json.dumps(cv_data, ensure_ascii=False, indent=2), encoding="utf-8")
    pdf_bytes = cv_generator._render_pdf(cv_data, role)
    cv_generator.output_path(refnr, role).write_bytes(pdf_bytes)
    return JSONResponse({"status": "saved"})


@app.post("/api/cv/{refnr}/render")
def api_cv_render(refnr: str, role: str = DEFAULT_ROLE) -> JSONResponse:
    """Re-render PDF from saved JSON (no Claude API call). Use after updating photo."""
    from jobfit.cv import generator as cv_generator

    json_path = cv_generator.output_json_path(refnr, role)
    if not json_path.exists():
        raise HTTPException(
            status_code=404,
            detail="CV not yet generated for this vacancy. Use POST /api/cv/{refnr}/generate first.",
        )

    cv_data = json.loads(json_path.read_text(encoding="utf-8"))
    pdf_bytes = cv_generator._render_pdf(cv_data, role)
    out = cv_generator.output_path(refnr, role)
    out.write_bytes(pdf_bytes)

    url = f"/api/cv/{quote(refnr, safe='')}/download?role={quote(role, safe='')}"
    return JSONResponse({"status": "ready", "url": url, "bytes": len(pdf_bytes)})


# ── Anschreiben generation ────────────────────────────────────────────────────

_GENERATING_ANSCHREIBEN: set[tuple[str, str]] = set()
_FAILED_ANSCHREIBEN: set[tuple[str, str]] = set()


async def _anschreiben_generate_bg(refnr: str, role: str, api_key: str) -> None:
    from jobfit.anschreiben import generator as anschreiben_generator

    try:
        await asyncio.to_thread(anschreiben_generator.generate, refnr, role, api_key)
        _FAILED_ANSCHREIBEN.discard((refnr, role))
    except Exception as exc:
        logger.error(f"Background Anschreiben generation failed for {refnr!r}: {exc}")
        _FAILED_ANSCHREIBEN.add((refnr, role))
    finally:
        _GENERATING_ANSCHREIBEN.discard((refnr, role))


@app.post("/api/anschreiben/{refnr}/generate")
async def api_anschreiben_generate(
    refnr: str, background_tasks: BackgroundTasks, role: str = DEFAULT_ROLE
) -> JSONResponse:
    """Queue Anschreiben generation as a background task; return immediately."""
    from jobfit.llm import resolve_key

    try:
        api_key = resolve_key(command_prefix="CV")
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    with get_session() as session:
        if session.get(JobModel, refnr) is None:
            raise HTTPException(status_code=404, detail=f"Job not found: {refnr}")

    from jobfit.anschreiben import generator as anschreiben_generator

    path = anschreiben_generator.output_path(refnr, role)
    if path.exists() and (time.time() - path.stat().st_mtime) < 86400:
        url = f"/api/anschreiben/{quote(refnr, safe='')}/download?role={quote(role, safe='')}"
        return JSONResponse({"status": "ready", "url": url})

    _GENERATING_ANSCHREIBEN.add((refnr, role))
    _FAILED_ANSCHREIBEN.discard((refnr, role))
    background_tasks.add_task(_anschreiben_generate_bg, refnr, role, api_key)
    return JSONResponse({"status": "queued"})


@app.get("/api/anschreiben/{refnr}/status")
def api_anschreiben_status(refnr: str, role: str = DEFAULT_ROLE) -> JSONResponse:
    """Check whether a generated Anschreiben PDF is ready for download."""
    from jobfit.anschreiben import generator as anschreiben_generator

    if (refnr, role) in _GENERATING_ANSCHREIBEN:
        return JSONResponse({"status": "generating"})

    if (refnr, role) in _FAILED_ANSCHREIBEN:
        return JSONResponse({"status": "failed"})

    path = anschreiben_generator.output_path(refnr, role)
    if path.exists():
        url = f"/api/anschreiben/{quote(refnr, safe='')}/download?role={quote(role, safe='')}"
        return JSONResponse({"status": "ready", "url": url})
    return JSONResponse({"status": "generating"})


@app.post("/api/anschreiben/{refnr}/archive")
def api_anschreiben_archive(refnr: str, role: str = DEFAULT_ROLE) -> JSONResponse:
    """Move current Anschreiben PDF + JSON to history/ with UTC timestamp."""
    import shutil
    from jobfit.anschreiben import generator as anschreiben_generator

    pdf = anschreiben_generator.output_path(refnr, role)
    json_path = anschreiben_generator.output_json_path(refnr, role)
    candidates = [p for p in (pdf, json_path) if p.exists()]
    if candidates:
        history_dir = pdf.parent / "history"
        history_dir.mkdir(exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        for path in candidates:
            shutil.move(str(path), str(history_dir / f"{path.stem}_{ts}{path.suffix}"))
    return JSONResponse({"status": "archived"})


@app.put("/api/anschreiben/{refnr}/json")
async def api_anschreiben_save_json(refnr: str, request: Request, role: str = DEFAULT_ROLE) -> JSONResponse:
    """Save edited Anschreiben JSON and re-render PDF (no LLM call)."""
    from jobfit.anschreiben import generator as anschreiben_generator

    body = await request.body()
    try:
        letter_data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")

    json_path = anschreiben_generator.output_json_path(refnr, role)
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="Anschreiben not found. Generate first.")

    json_path.write_text(json.dumps(letter_data, ensure_ascii=False, indent=2), encoding="utf-8")
    pdf_bytes = anschreiben_generator._render_pdf(letter_data)
    anschreiben_generator.output_path(refnr, role).write_bytes(pdf_bytes)
    return JSONResponse({"status": "saved"})


@app.post("/api/anschreiben/{refnr}/render")
def api_anschreiben_render(refnr: str, role: str = DEFAULT_ROLE) -> JSONResponse:
    """Re-render PDF from saved JSON (no LLM call)."""
    from jobfit.anschreiben import generator as anschreiben_generator

    json_path = anschreiben_generator.output_json_path(refnr, role)
    if not json_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Anschreiben not yet generated. Use POST /api/anschreiben/{refnr}/generate first.",
        )
    letter_data = json.loads(json_path.read_text(encoding="utf-8"))
    pdf_bytes = anschreiben_generator._render_pdf(letter_data)
    out = anschreiben_generator.output_path(refnr, role)
    out.write_bytes(pdf_bytes)
    url = f"/api/anschreiben/{quote(refnr, safe='')}/download?role={quote(role, safe='')}"
    return JSONResponse({"status": "ready", "url": url, "bytes": len(pdf_bytes)})


@app.get("/api/anschreiben/{refnr}/preview")
def api_anschreiben_preview(refnr: str, role: str = DEFAULT_ROLE) -> HTMLResponse:
    """Render saved Anschreiben JSON as HTML (no LLM call)."""
    from jobfit.anschreiben import generator as anschreiben_generator
    from jobfit.anschreiben.generator.render import _render_html

    json_path = anschreiben_generator.output_json_path(refnr, role)
    if not json_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Anschreiben not yet generated. Use POST /api/anschreiben/{refnr}/generate first.",
        )
    letter_data = json.loads(json_path.read_text(encoding="utf-8"))
    return HTMLResponse(content=_render_html(letter_data, refnr=refnr, role=role))


@app.get("/api/anschreiben/{refnr}/download")
def api_anschreiben_download(refnr: str, role: str = DEFAULT_ROLE) -> Response:
    """Serve a previously generated Anschreiben PDF from disk."""
    from jobfit.anschreiben import generator as anschreiben_generator

    path = anschreiben_generator.output_path(refnr, role)
    if not path.exists():
        raise HTTPException(
            status_code=404, detail="Anschreiben not yet generated for this vacancy"
        )

    return Response(
        content=path.read_bytes(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{path.name}"'},
    )


# ── Cache management ──────────────────────────────────────────────────────────


@app.post("/api/cache/rebuild")
async def cache_rebuild() -> dict[str, Any]:
    """Rebuild all dashboards in the background (no-op if already rebuilding)."""
    _ = create_task(build_all())
    return {"ok": True, "message": "Cache cleared, rebuilding dashboards in background"}


# ── Entry point ───────────────────────────────────────────────────────────────


def serve() -> None:
    import uvicorn

    from jobfit._log import intercept_stdlib_logging
    from jobfit._log import setup as log_setup

    log_setup("serve")
    intercept_stdlib_logging("uvicorn", "uvicorn.error", "uvicorn.access")
    uvicorn.run(app, host="127.0.0.1", port=8888, log_config=None)
