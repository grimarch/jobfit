"""Classify known IT brands among product companies in the dataset.

Sends all unique enterprise/mittelstand company names to Claude in a single request
and saves the result to the known_brands table in the DB. Used by the Target Companies
dashboard to assign the CV Builder tier.

The system prompt is read from data/{role}/input/brands_prompt.txt — edit it to match
the role's community and brand criteria.

Run when new enterprise/mittelstand companies appear in the dataset (after classify).
"""

import json

from loguru import logger

from jobfit.config import role_input_dir
from jobfit.llm import complete as llm_complete
from jobfit.llm import resolve_key, resolve_model
from jobfit.roles import DEFAULT_ROLE


def _load_prompt(role_slug: str) -> str:
    prompt_file = role_input_dir(role_slug) / "brands_prompt.txt"
    if not prompt_file.exists():
        raise SystemExit(
            f"Missing: {prompt_file}\n"
            f"Create it with role-specific brand criteria for Claude."
        )
    return prompt_file.read_text(encoding="utf-8").strip()


def collect_firma_names(role_slug: str) -> list[str]:
    from jobfit.db import get_session
    from jobfit.db.models import Classification as ClsModel

    with get_session() as session:
        rows = (
            session.query(ClsModel)
            .filter(
                ClsModel.role == role_slug,
                ClsModel.company_type == "product",
                ClsModel.company_stage.in_(("enterprise", "mittelstand")),
            )
            .all()
        )

    return sorted({(r.firma or "").strip() for r in rows if (r.firma or "").strip()})


def classify_brands(firma_names: list[str], system_prompt: str) -> list[str]:
    api_key = resolve_key()
    model = resolve_model("BRANDS_MODEL")
    raw = llm_complete(
        [{"role": "user", "content": json.dumps(firma_names, ensure_ascii=False)}],
        system=system_prompt,
        model=model,
        api_key=api_key,
        fallback_model_var="BRANDS_FALLBACK_MODEL",
    ).strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    if not raw:
        logger.error("LLM returned empty response")
        return []
    return json.loads(raw)


def has_any(role_slug: str) -> bool:
    """Return True if any known_brands entries exist for this role."""
    from jobfit.db import get_session
    from jobfit.db.models import KnownBrand

    with get_session() as session:
        return (
            session.query(KnownBrand).filter(KnownBrand.role == role_slug).first()
            is not None
        )


def _already_evaluated(role_slug: str) -> frozenset[str]:
    from jobfit.db import get_session
    from jobfit.db.models import KnownBrand

    with get_session() as session:
        rows = session.query(KnownBrand).filter(KnownBrand.role == role_slug).all()
    return frozenset(r.firma for r in rows)


def _clear(role_slug: str) -> None:
    from jobfit.db import get_session
    from jobfit.db.models import KnownBrand

    with get_session() as session:
        session.query(KnownBrand).filter(KnownBrand.role == role_slug).delete()


def save(known: list[str], rejected: list[str], role_slug: str) -> None:
    from jobfit.db import get_session
    from jobfit.db.models import KnownBrand

    with get_session() as session:
        for firma in known:
            session.add(KnownBrand(role=role_slug, firma=firma, is_known=True))
        for firma in rejected:
            session.add(KnownBrand(role=role_slug, firma=firma, is_known=False))


def clean_stale(args: object) -> None:
    """Remove known_brands entries for firms no longer in enterprise/mittelstand product. No LLM calls."""
    from jobfit.db import get_session
    from jobfit.db.models import Classification as ClsModel
    from jobfit.db.models import KnownBrand

    role_slug = getattr(args, "role", DEFAULT_ROLE)

    with get_session() as session:
        brand_rows = (
            session.query(KnownBrand).filter(KnownBrand.role == role_slug).all()
        )
        cls_rows = (
            session.query(ClsModel)
            .filter(
                ClsModel.role == role_slug,
                ClsModel.company_type == "product",
                ClsModel.company_stage.in_(("enterprise", "mittelstand")),
            )
            .all()
        )

    current_firms = frozenset(
        (r.firma or "").strip() for r in cls_rows if (r.firma or "").strip()
    )
    stale_firmas = [r.firma for r in brand_rows if r.firma not in current_firms]

    if not stale_firmas:
        logger.info("No stale entries to remove.")
        return

    with get_session() as session:
        session.query(KnownBrand).filter(
            KnownBrand.role == role_slug,
            KnownBrand.firma.in_(stale_firmas),
        ).delete(synchronize_session=False)

    logger.info(f"Removed {len(stale_firmas)} stale entries from known_brands.")


def audit(args: object) -> None:
    """Show known_brands anomalies: duplicates, stale entries, missing evaluations. No LLM calls."""
    from collections import Counter

    from jobfit.db import get_session
    from jobfit.db.models import Classification as ClsModel
    from jobfit.db.models import KnownBrand

    role_slug = getattr(args, "role", DEFAULT_ROLE)

    with get_session() as session:
        brand_rows = (
            session.query(KnownBrand).filter(KnownBrand.role == role_slug).all()
        )
        cls_rows = (
            session.query(ClsModel)
            .filter(
                ClsModel.role == role_slug,
                ClsModel.company_type == "product",
                ClsModel.company_stage.in_(("enterprise", "mittelstand")),
            )
            .all()
        )

    # Duplicates: same firma, multiple rows
    firma_counts = Counter(r.firma for r in brand_rows)
    dupes = {f: n for f, n in firma_counts.items() if n > 1}
    if dupes:
        logger.warning(f"Duplicate entries in known_brands ({len(dupes)} companies):")
        for firma, n in sorted(dupes.items()):
            logger.warning(f"  {n}x  {firma}")
    else:
        logger.info("No duplicates in known_brands.")

    # Stale: in known_brands but no longer enterprise/mittelstand product
    current_firms = frozenset(
        (r.firma or "").strip() for r in cls_rows if (r.firma or "").strip()
    )
    stale = sorted({r.firma for r in brand_rows if r.firma not in current_firms})
    if stale:
        logger.warning(f"Stale entries ({len(stale)} firms no longer in dataset):")
        for firma in stale:
            logger.warning(f"  {firma}")
    else:
        logger.info("No stale entries in known_brands.")

    # Missing: in dataset but not yet evaluated
    evaluated = frozenset(r.firma for r in brand_rows)
    missing = sorted(current_firms - evaluated)
    if missing:
        logger.warning(
            f"Not yet evaluated ({len(missing)} firms — run: jobfit brands --role {role_slug}):"
        )
        for firma in missing:
            logger.warning(f"  {firma}")
    else:
        logger.info("All enterprise/mittelstand companies evaluated.")


def run(args: object) -> None:
    role_slug = getattr(args, "role", DEFAULT_ROLE)
    dry_run = getattr(args, "dry_run", False)
    force = getattr(args, "force", False)

    firms = collect_firma_names(role_slug)
    logger.info(
        f"Collected {len(firms)} unique product company names (enterprise + mittelstand)"
    )

    if dry_run:
        for f in firms:
            print(f)
        print(f"\n(dry-run: {len(firms)} names, no API call)")
        return

    if force:
        _clear(role_slug)
        logger.info("--force: cleared existing known_brands, re-evaluating all")
        new_firms = firms
    else:
        evaluated = _already_evaluated(role_slug)
        new_firms = [f for f in firms if f not in evaluated]
        if evaluated:
            logger.info(f"Skipping {len(evaluated)} already-evaluated companies")

    if not new_firms:
        logger.info("No new companies to evaluate.")
        return

    prompt = _load_prompt(role_slug)
    logger.info(f"Sending {len(new_firms)} new companies to LLM...")
    known = classify_brands(new_firms, prompt)
    logger.info(f"Known brands identified: {len(known)}")
    for name in known:
        logger.info(f"  ✓ {name}")

    from jobfit.dashboards.scoring import norm_firma as _norm_firma

    known_norms = frozenset(_norm_firma(k) for k in known)
    rejected = [f for f in new_firms if _norm_firma(f) not in known_norms]
    save(known, rejected, role_slug)
    logger.info(
        f"Saved {len(known)} known + {len(rejected)} rejected brands to DB (role={role_slug})"
    )
