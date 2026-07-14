"""HTML/PDF rendering for tailored CV documents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from jobfit.config import role_input_dir

__all__ = ["_load_photo", "_render_html", "_render_pdf"]

_CV_KEY_ORDER = ["language", "name", "headline", "contact", "summary",
                 "experience", "skills", "education", "certifications",
                 "languages", "tailoring_notes", "_model"]
_EXP_KEY_ORDER = ["title", "company", "location", "period", "bullets"]
_CONTACT_KEY_ORDER = ["city", "email", "phone", "linkedin", "xing", "github"]
_SKILL_KEY_ORDER = ["category", "items"]
_EDU_KEY_ORDER = ["degree", "institution", "location", "period"]
_LANG_KEY_ORDER = ["language", "level"]


def _reorder(d: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    result = {k: d[k] for k in keys if k in d}
    result.update({k: v for k, v in d.items() if k not in result})
    return result


def _ordered_cv(cv_data: dict[str, Any]) -> dict[str, Any]:
    """Return cv_data with keys in canonical CV document order."""
    out = _reorder(cv_data, _CV_KEY_ORDER)
    if "contact" in out:
        out["contact"] = _reorder(out["contact"], _CONTACT_KEY_ORDER)
    if "experience" in out:
        out["experience"] = [_reorder(e, _EXP_KEY_ORDER) for e in out["experience"]]
    if "skills" in out:
        out["skills"] = [_reorder(s, _SKILL_KEY_ORDER) for s in out["skills"]]
    if "education" in out:
        out["education"] = [_reorder(e, _EDU_KEY_ORDER) for e in out["education"]]
    if "languages" in out:
        out["languages"] = [_reorder(lang, _LANG_KEY_ORDER) for lang in out["languages"]]
    return out


def _load_photo(role_slug: str) -> str | None:
    """Return base64 data URI for data/{role}/input/bewerbungsfoto.{jpg,jpeg,png} if found."""
    import base64

    for ext in ("jpg", "jpeg", "png"):
        path = role_input_dir(role_slug) / f"bewerbungsfoto.{ext}"
        if path.exists():
            mime = "image/png" if ext == "png" else "image/jpeg"
            data = base64.b64encode(path.read_bytes()).decode()
            return f"data:{mime};base64,{data}"
    return None


def _render_html(
    cv_data: dict[str, Any],
    ats_report: Any = None,
    photo_b64: str | None = None,
    refnr: str | None = None,
    role: str | None = None,
) -> str:
    """Render cv_data to HTML using cv_print.html Jinja2 template."""
    from markupsafe import Markup

    templates_dir = Path(__file__).resolve().parent.parent / "templates"
    env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)
    template = env.get_template("cv_print.html")
    cv_json = Markup(json.dumps(_ordered_cv(cv_data), ensure_ascii=False, indent=2).replace("</", "<\\/"))
    return template.render(
        cv=cv_data, ats=ats_report, photo=photo_b64, refnr=refnr, role=role,
        model=cv_data.get("_model"),
        cv_json=cv_json,
    )


def _render_pdf(cv_data: dict[str, Any], role_slug: str) -> bytes:
    """Render cv_data to PDF bytes via WeasyPrint."""
    import weasyprint  # imported lazily — only needed at render time
    from weasyprint.text.fonts import FontConfiguration

    photo_b64 = _load_photo(role_slug)
    html_str = _render_html(cv_data, photo_b64=photo_b64)
    font_config = FontConfiguration()
    pdf_bytes = weasyprint.HTML(string=html_str).write_pdf(font_config=font_config)
    if pdf_bytes is None:
        raise RuntimeError("WeasyPrint failed to render PDF")
    return pdf_bytes
