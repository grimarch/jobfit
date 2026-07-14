"""HTML/PDF rendering for tailored Anschreiben documents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

__all__ = ["_render_html", "_render_pdf"]


def _render_html(
    letter_data: dict[str, Any],
    refnr: str | None = None,
    role: str | None = None,
) -> str:
    """Render letter_data to HTML using anschreiben_print.html Jinja2 template."""
    from markupsafe import Markup

    templates_dir = Path(__file__).resolve().parent.parent / "templates"
    env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)
    template = env.get_template("anschreiben_print.html")
    letter_json = Markup(
        json.dumps(letter_data, ensure_ascii=False, indent=2).replace("</", "<\\/")
    )
    return template.render(
        letter=letter_data,
        refnr=refnr,
        role=role,
        model=letter_data.get("_model"),
        letter_json=letter_json,
    )


def _render_pdf(letter_data: dict[str, Any]) -> bytes:
    """Render letter_data to PDF bytes via WeasyPrint."""
    import weasyprint
    from weasyprint.text.fonts import FontConfiguration

    html_str = _render_html(letter_data)
    font_config = FontConfiguration()
    pdf_bytes = weasyprint.HTML(string=html_str).write_pdf(font_config=font_config)
    if pdf_bytes is None:
        raise RuntimeError("WeasyPrint failed to render PDF")
    return pdf_bytes
