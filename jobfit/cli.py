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
