"""Human-readable terminal rendering for --print-prompt output."""

from __future__ import annotations

import json
import re
import sys
from typing import Any

_PRIVACY_TOKEN_RE = re.compile(
    r"\[(?:CANDIDATE_NAME|EMAIL|PHONE|GITHUB|LINKEDIN|XING|"
    r"CITY|POSTAL_CODE|COUNTRY|WORK_LOC_\d+|WORK_COMP_\d+|"
    r"EDU_LOC_\d+|EDU_INST_\d+|EDU_CITY)\]",
)
_SECTION_HEADER_RE = re.compile(r"^## (.+)$")
_KV_SECTIONS = frozenset({
    "JOB CONTEXT",
    "APPLICATION REQUIREMENTS",
})
_MARKDOWN_SECTIONS = frozenset({
    "JOB DESCRIPTION",
    "PRIVACY PLACEHOLDERS",
    "CANDIDATE CONTEXT",
})
_JSON_SECTIONS = frozenset({
    "CANDIDATE PROFILE (structured metadata)",
    "OUTPUT SCHEMA",
})
_CV_SECTIONS = frozenset({
    "CANDIDATE CV (source of truth — do not add anything not present here)",
    "CANDIDATE CV (source of truth for skills and work experience)",
})


def split_prompt_sections(prompt: str) -> list[tuple[str, str]]:
    """Split a user prompt into (title, body) sections by markdown ## headers."""
    sections: list[tuple[str, str]] = []
    title = "Preamble"
    body_lines: list[str] = []

    for line in prompt.splitlines():
        if m := _SECTION_HEADER_RE.match(line):
            if body_lines or title != "Preamble":
                sections.append((title, "\n".join(body_lines).strip()))
            title = m.group(1).strip()
            body_lines = []
            continue
        body_lines.append(line)

    if body_lines or title != "Preamble":
        sections.append((title, "\n".join(body_lines).strip()))
    return sections


def estimate_tokens(text: str) -> int:
    """Rough token estimate for display (chars / 4)."""
    return max(1, len(text) // 4)


def _highlight_privacy_tokens(text: str) -> Any:
    from rich.text import Text

    rendered = Text()
    last = 0
    for match in _PRIVACY_TOKEN_RE.finditer(text):
        if match.start() > last:
            rendered.append(text[last:match.start()])
        rendered.append(match.group(0), style="bold magenta")
        last = match.end()
    rendered.append(text[last:])
    return rendered


def _try_parse_json(body: str) -> str | None:
    stripped = body.strip()
    if not stripped:
        return None
    try:
        json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return stripped


def _render_key_value_section(body: str) -> Any:
    from rich.table import Table
    from rich.text import Text

    table = Table(show_header=False, box=None, pad_edge=False, padding=(0, 1))
    table.add_column("field", style="cyan", no_wrap=True)
    table.add_column("value")

    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if ":" not in stripped:
            table.add_row("", stripped)
            continue
        key, _, value = stripped.partition(":")
        value_cell: str | Text = value.strip()
        if key.strip() == "Skill coverage":
            value_cell = Text(value.strip(), style="bold green")
        table.add_row(key.strip(), value_cell)
    return table


def _render_section(title: str, body: str) -> Any:
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.syntax import Syntax

    if title in _KV_SECTIONS:
        return Panel(_render_key_value_section(body), title=title, border_style="cyan")

    if title in _MARKDOWN_SECTIONS:
        return Panel(Markdown(body), title=title, border_style="blue")

    if title in _JSON_SECTIONS:
        payload = _try_parse_json(body)
        if payload is not None:
            content = Syntax(payload, "json", theme="monokai", word_wrap=True)
        else:
            content = _highlight_privacy_tokens(body)
        return Panel(content, title=title, border_style="green")

    if title in _CV_SECTIONS:
        return Panel(
            _highlight_privacy_tokens(body),
            title=title,
            border_style="yellow",
        )

    if title == "SKILL ANALYSIS":
        return Panel(_highlight_privacy_tokens(body), title=title, border_style="magenta")

    if title == "Preamble" and not body:
        return None

    return Panel(_highlight_privacy_tokens(body), title=title, border_style="dim")


def print_llm_prompt(
    *,
    system: str,
    user: str,
    refnr: str,
    doc_label: str,
    model: str,
    provider: str,
) -> None:
    """Render system + user prompts for --print-prompt."""
    use_rich = sys.stdout.isatty()
    if use_rich:
        _print_rich_prompt(
            system=system,
            user=user,
            refnr=refnr,
            doc_label=doc_label,
            model=model,
            provider=provider,
        )
    else:
        _print_plain_prompt(
            system=system,
            user=user,
            refnr=refnr,
            doc_label=doc_label,
            model=model,
            provider=provider,
        )


def _print_plain_prompt(
    *,
    system: str,
    user: str,
    refnr: str,
    doc_label: str,
    model: str,
    provider: str,
) -> None:
    system_tokens = estimate_tokens(system)
    user_tokens = estimate_tokens(user)
    print(
        f"=== {doc_label} prompt === refnr={refnr} "
        f"provider={provider} model={model} "
        f"~{system_tokens + user_tokens:,} tokens "
        f"(system ~{system_tokens:,}, user ~{user_tokens:,})"
    )
    print("\n--- SYSTEM ---\n")
    print(system)
    print("\n--- USER ---\n")
    for title, body in split_prompt_sections(user):
        print(f"## {title}")
        print(body)
        print()


def _print_rich_prompt(
    *,
    system: str,
    user: str,
    refnr: str,
    doc_label: str,
    model: str,
    provider: str,
    console: Any | None = None,
) -> None:
    from rich.console import Console
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.table import Table

    if console is None:
        console = Console()
    system_tokens = estimate_tokens(system)
    user_tokens = estimate_tokens(user)

    meta = Table.grid(padding=(0, 2))
    meta.add_column(style="bold")
    meta.add_column()
    meta.add_row("Document", doc_label)
    meta.add_row("RefNr", refnr)
    meta.add_row("Provider", provider)
    meta.add_row("Model", model)
    meta.add_row("Tokens (est.)", f"~{system_tokens + user_tokens:,} total")
    meta.add_row("", f"system ~{system_tokens:,} · user ~{user_tokens:,}")

    console.print(Panel(meta, title="LLM Prompt Preview", border_style="bright_blue"))
    console.print(Rule("system", style="bold yellow"))
    console.print(Panel(system, border_style="yellow"))

    console.print(Rule("user", style="bold cyan"))
    for title, body in split_prompt_sections(user):
        rendered = _render_section(title, body)
        if rendered is not None:
            console.print(rendered)
            console.print()
