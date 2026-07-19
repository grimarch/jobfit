"""CLI entry point for jobfit."""

import argparse

import click

from jobfit import (
    brands, cache, classify, dashboards, enrich, fetchers, mark_closed, sync, verify_urls,
)
from jobfit._log import setup as log_setup
from jobfit.roles import DEFAULT_ROLE, ROLES
from jobfit.utils import generate_doc

_ns = argparse.Namespace

role_option = click.option(
    "--role",
    default=DEFAULT_ROLE,
    type=click.Choice(list(ROLES)),
    metavar="ROLE",
    help=f"Job role profile (default: {DEFAULT_ROLE})",
)


@click.group()
@click.pass_context
def cli(ctx: click.Context) -> None:
    """German job market analyzer."""
    log_setup(ctx.invoked_subcommand or "")


@cli.command(name="classify")
@click.option("--limit", type=int, metavar="N", help="Process only N jobs")
@click.option("--audit", is_flag=True, help="Show inconsistencies, no LLM calls")
@role_option
def cmd_classify(limit: int | None, audit: bool, role: str) -> None:
    args = _ns(role_obj=ROLES[role], limit=limit)
    classify.audit(args) if audit else classify.run(args)


@cli.command(name="brands")
@click.option("--dry-run", is_flag=True, help="Print company names, no API call")
@click.option("--audit", is_flag=True, help="Show duplicates and stale entries")
@click.option("--clean-stale", is_flag=True, help="Remove stale known_brands entries")
@click.option("--force", is_flag=True, help="Re-evaluate all companies from scratch")
@role_option
def cmd_brands(dry_run: bool, audit: bool, clean_stale: bool, force: bool, role: str) -> None:
    args = _ns(role=role, dry_run=dry_run, force=force)
    if audit:
        brands.audit(args)
    elif clean_stale:
        brands.clean_stale(args)
    else:
        brands.run(args)


@cli.command(name="sync")
@role_option
def cmd_sync(role: str) -> None:
    sync.run(role)


@cli.command(name="serve")
@click.argument("action", type=click.Choice(["rebuild", "sync"]))
@role_option
def cmd_serve(action: str, role: str) -> None:
    if action == "sync":
        sync.run_for_serve(role)
    cache.trigger_rebuild()


@cli.command(name="dashboard")
@click.argument("target", type=click.Choice(["all", "analyze", "cv", "listings", "targets"]))
@role_option
def cmd_dashboard(target: str, role: str) -> None:
    enrich.run(ROLES[role])
    dashboards.run_cmd(target, ROLES[role])


@cli.command(name="fetch")
@click.argument("source", type=click.Choice(["all", "jobhive", "softgarden", "ba", "everjobs"]))
@click.option("--dry-run", is_flag=True, help="Print counts, don't write files")
@click.option("--force-refresh", is_flag=True, help="Re-download cached files")
@click.option("--days", type=int, default=60, metavar="N", help="BA: days back (default: 60)")
@click.option("--ats", multiple=True, metavar="ATS", help="jobhive: limit to ATS platforms")
@click.option("--stats-out", metavar="FILE", help="jobhive: save per-ATS counts to JSON")
@role_option
def cmd_fetch(source: str, dry_run: bool, force_refresh: bool, days: int, ats: tuple[str, ...], stats_out: str | None, role: str) -> None:
    args = _ns(
        role_obj=ROLES[role], dry_run=dry_run, force_refresh=force_refresh,
        days=days, ats=list(ats) or None, stats_out=stats_out,
    )
    fetchers.run_source(source, args)


@cli.group(name="cv")
def cv_group() -> None:
    """CV management commands."""


@cv_group.command(name="extract")
@click.argument("file")
@role_option
def cmd_cv_extract(file: str, role: str) -> None:
    from jobfit.cv import extract as cv_extract
    cv_extract.run(_ns(file=file, role_obj=ROLES[role]))


@cv_group.command(name="generate")
@click.argument("refnr")
@click.option("--output", metavar="PATH", help="Output path (default: auto)")
@click.option("--open", "open_after", is_flag=True, help="Open in system viewer")
@click.option("--html", is_flag=True, help="Output HTML instead of PDF")
@click.option("--preview", is_flag=True, help="Render from existing JSON, no LLM")
@click.option("--print-prompt", "print_prompt", is_flag=True, help="Print formatted LLM prompt (system + user)")
@click.option("--save-prompt", "save_prompt", is_flag=False, flag_value="__auto__", default=None, metavar="PATH", help="Save LLM prompt to file and exit; PATH optional (.md or .json, default: $JOBFIT_DATA_DIR/../prompts/)")
@role_option
def cmd_cv_generate(refnr: str, output: str | None, open_after: bool, html: bool, preview: bool, print_prompt: bool, save_prompt: str | None, role: str) -> None:
    from jobfit.cv import generator as cv_generator
    generate_doc(cv_generator, refnr, output, open_after, html, preview, print_prompt, ROLES[role], save_prompt)


@cv_group.command(name="anschreiben")
@click.argument("refnr")
@click.option("--output", metavar="PATH", help="Output path (default: auto)")
@click.option("--open", "open_after", is_flag=True, help="Open in system viewer")
@click.option("--html", is_flag=True, help="Output HTML instead of PDF")
@click.option("--preview", is_flag=True, help="Render from existing JSON, no LLM")
@click.option("--print-prompt", "print_prompt", is_flag=True, help="Print formatted LLM prompt (system + user)")
@click.option("--save-prompt", "save_prompt", is_flag=False, flag_value="__auto__", default=None, metavar="PATH", help="Save LLM prompt to file and exit; PATH optional (.md or .json, default: $JOBFIT_DATA_DIR/../prompts/)")
@role_option
def cmd_cv_anschreiben(refnr: str, output: str | None, open_after: bool, html: bool, preview: bool, print_prompt: bool, save_prompt: str | None, role: str) -> None:
    from jobfit.anschreiben import generator as anschreiben_generator
    generate_doc(anschreiben_generator, refnr, output, open_after, html, preview, print_prompt, ROLES[role], save_prompt)


@cli.command(name="enrich")
@click.option("--dry-run", is_flag=True, help="Detect fields, print counts, don't write")
@click.option("--audit", is_flag=True, help="Show current enrich stats from DB")
@role_option
def cmd_enrich(dry_run: bool, audit: bool, role: str) -> None:
    role_obj = ROLES[role]
    enrich.audit(role_obj) if audit else enrich.run(role_obj, dry_run=dry_run)


@cli.command(name="mark-closed")
@click.option("--dry-run", is_flag=True, help="Print what would be closed, don't write")
@role_option
def cmd_mark_closed(dry_run: bool, role: str) -> None:
    mark_closed.run(_ns(role_obj=ROLES[role], dry_run=dry_run))


@cli.command(name="verify-urls")
@click.option("--dry-run", is_flag=True, help="Print what would be closed, don't write")
@role_option
def cmd_verify_urls(dry_run: bool, role: str) -> None:
    verify_urls.run(_ns(role_obj=ROLES[role], dry_run=dry_run))


@cli.group(name="prep-context")
def prep_context_group() -> None:
    """Prep context export for interview preparation."""


@prep_context_group.command(name="export")
@role_option
@click.option(
    "--cv",
    "cv_path",
    default=None,
    metavar="PATH",
    help="CV file for overlap/gaps (default: role CV via cv_read). Use prompts/CV.md for interview truth.",
)
@click.option(
    "--out",
    "out_path",
    default="prompts/prep_context.md",
    metavar="PATH",
    show_default=True,
    help="Output path for the Markdown file.",
)
@click.option(
    "--jd-excerpt-chars",
    default=400,
    metavar="N",
    show_default=True,
    help="Max chars of anonymized JD excerpt per starred job (0 = omit excerpts).",
)
@click.option(
    "--market-scope",
    default="sm",
    type=click.Choice(["sm", "startup", "mittelstand", "enterprise"]),
    show_default=True,
    help="Stage scope for market snapshot (sm = startup+mittelstand).",
)
@click.option(
    "--include-closed",
    is_flag=True,
    help="Include starred jobs with jobs.closed_at set.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print summary counts; write nothing.",
)
@click.option(
    "--no-merge",
    "no_merge",
    is_flag=True,
    help="Overwrite --out without merging existing why_starred / prep_label values.",
)
def cmd_prep_context_export(
    role: str,
    cv_path: str | None,
    out_path: str,
    jd_excerpt_chars: int,
    market_scope: str,
    include_closed: bool,
    dry_run: bool,
    no_merge: bool,
) -> None:
    """Export an anonymized Markdown prep context for interview preparation.

    Starred jobs use the same sort_key as the targets Starred tab (S1 = top UI row).
    Company names are redacted in JD excerpts; match rows via order, title/score, or refnr.

    If --out already exists, human-edited why_starred and prep_label values are
    merged back by refnr. Use --no-merge to skip this and overwrite from scratch.
    """
    from pathlib import Path
    from jobfit.prep_context import export as prep_export

    prep_export.run(
        role_slug=role,
        cv_path=Path(cv_path) if cv_path else None,
        out_path=Path(out_path),
        jd_excerpt_chars=jd_excerpt_chars,
        market_scope=market_scope,
        include_closed=include_closed,
        dry_run=dry_run,
        no_merge=no_merge,
    )
