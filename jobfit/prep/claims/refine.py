"""LLM refine for prep claims draft → claims.llm.md."""

from __future__ import annotations

import re
from pathlib import Path

from loguru import logger

from jobfit.llm import complete as llm_complete, resolve_key, resolve_model, resolve_provider
from jobfit.prep.claims.draft import default_draft_path, extract_llm_input
from jobfit.prep.prompts_util import load_system_prompt, strip_markdown_fences

_COMMAND_PREFIX = "PREP_CLAIMS"
_MODEL_VAR = "PREP_CLAIMS_MODEL"
_FALLBACK_MODEL_VAR = "PREP_CLAIMS_FALLBACK_MODEL"
PROMPT_DOC_LABEL = "Prep claims refine"
PROMPT_MODEL_VAR = _MODEL_VAR
PROMPT_COMMAND_PREFIX = _COMMAND_PREFIX

_GAPS_BEGIN = "<!-- jobfit:prep-claims:gaps -->"
_GAPS_END = "<!-- /jobfit:prep-claims:gaps -->"
_SYSTEM_MARKER = "## System / user prompt"
_AFTER_LLM_MARKER = "## After LLM"


def default_llm_path(role_slug: str) -> Path:
    return Path(f"prompts/prep/{role_slug}") / "claims.llm.md"


def default_prompt_path(role_slug: str) -> Path:
    return Path(f"prompts/prep/{role_slug}") / "claims_review_prompt.md"


def build_user_prompt(*, cv_text: str, draft_text: str) -> str:
    return "\n".join(
        [
            "## CANDIDATE CV (source of truth — do not add anything not present here)",
            "",
            cv_text.strip(),
            "",
            "## CLAIMS DRAFT (preserve structure; do not change Gaps Jobs/Count)",
            "",
            draft_text.strip(),
            "",
            "Return the full refined markdown document only. No preamble.",
        ]
    )


def validate_refine_output(draft_text: str, refined_text: str) -> list[str]:
    warnings: list[str] = []
    if not refined_text.lstrip().startswith("#"):
        warnings.append("Output does not start with a markdown heading")
    if _GAPS_BEGIN in draft_text and _GAPS_BEGIN not in refined_text:
        warnings.append("Gaps HTML markers missing in LLM output")
    if _GAPS_END in draft_text and _GAPS_END not in refined_text:
        warnings.append("Gaps closing marker missing in LLM output")
    if "**Draft**" not in refined_text and "**Reviewed:**" not in refined_text:
        warnings.append("Output header missing Draft/Reviewed marker")
    return warnings


def prepare_prompts(
    *,
    cv_path: Path,
    draft_path: Path,
    prompt_path: Path,
) -> tuple[str, str]:
    if not cv_path.is_file():
        raise FileNotFoundError(f"CV not found: {cv_path}")
    if not draft_path.is_file():
        raise FileNotFoundError(f"Draft not found: {draft_path} — run prep-claims draft first")
    if not prompt_path.is_file():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    system = load_system_prompt(prompt_path)
    raw_draft = draft_path.read_text(encoding="utf-8")
    user = build_user_prompt(
        cv_text=cv_path.read_text(encoding="utf-8"),
        draft_text=extract_llm_input(raw_draft),
    )
    return system, user


def run(
    *,
    role_slug: str,
    cv_path: Path,
    draft_path: Path,
    out_path: Path,
    prompt_path: Path,
    api_key: str | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, object]:
    if out_path.exists() and not force and not dry_run:
        raise FileExistsError(f"{out_path} exists — use --force to overwrite")

    system, user = prepare_prompts(cv_path=cv_path, draft_path=draft_path, prompt_path=prompt_path)
    summary: dict[str, object] = {
        "role": role_slug,
        "cv": str(cv_path),
        "draft": str(draft_path),
        "out": str(out_path),
        "prompt": str(prompt_path),
        "system_chars": len(system),
        "user_chars": len(user),
    }

    if dry_run:
        summary["mode"] = "dry-run"
        logger.info(
            "prep-claims refine dry-run: role={} out={} system_chars={} user_chars={}",
            role_slug,
            out_path,
            len(system),
            len(user),
        )
        return summary

    key = api_key or resolve_key(command_prefix=_COMMAND_PREFIX)
    model = resolve_model(_MODEL_VAR)
    provider = resolve_provider(_COMMAND_PREFIX)
    logger.info("prep-claims refine: role={} model={} provider={}", role_slug, model, provider)

    draft_text = draft_path.read_text(encoding="utf-8")
    raw = llm_complete(
        [{"role": "user", "content": user}],
        system=system,
        model=model,
        api_key=key,
        max_tokens=16384,
        fallback_model_var=_FALLBACK_MODEL_VAR,
        command_prefix=_COMMAND_PREFIX,
    )
    refined = strip_markdown_fences(raw)
    if not refined:
        raise RuntimeError("LLM returned empty output")

    warnings = validate_refine_output(draft_text, refined)
    for warning in warnings:
        logger.warning("prep-claims refine: {}", warning)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(refined + "\n", encoding="utf-8")
    summary.update(
        {
            "mode": "write",
            "out_chars": len(refined),
            "warnings": warnings,
            "model": model,
            "provider": provider,
        }
    )
    logger.info(
        "prep-claims refine: wrote {} ({} chars, {} warnings)",
        out_path,
        len(refined),
        len(warnings),
    )
    return summary


def default_draft_input_path(role_slug: str) -> Path:
    """Default --in for refine (same as draft --out)."""
    return default_draft_path(role_slug)
