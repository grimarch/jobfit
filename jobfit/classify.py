"""Classify job listings by company type (product vs consulting) and stage."""

import argparse
import json
import os
import sys
from typing import Any

import openai as _openai
from dotenv import load_dotenv
from loguru import logger
from tqdm import tqdm

from jobfit.llm import complete as llm_complete, resolve_key, resolve_model
from jobfit.industry import CANONICAL, update_unmatched
from jobfit.roles import DEFAULT_ROLE, ROLES, Role

load_dotenv()

_CANONICAL_STR = ", ".join(CANONICAL[:-1])  # exclude "Other" — model uses it implicitly

SYSTEM_PROMPT = (
    "Classify German job listings by company type and stage."
    " Return only valid JSON, no explanation.\n\n"
    'Output format:\n'
    '{\n'
    '  "company_type": "product" | "consulting" | "public_sector" | "unknown",\n'
    '  "company_stage": "startup" | "mittelstand" | "enterprise" | "public_sector" | "unknown",\n'
    '  "industry": "<short English label>"\n'
    '}\n\n'
    "company_type — use ONLY these exact values:\n"
    '- "product": company builds and sells their own product or service (SaaS, platform, app, etc.)\n'
    '- "consulting": IT consulting firm, staffing agency, or posting on behalf of a client\n'
    '- "public_sector": government agency, university, municipality, public institution\n'
    '- "unknown": cannot determine from available information\n\n'
    "company_stage — use ONLY these exact values:\n"
    '- "startup": young company, typically < 200 employees, mentions "scale-up", "fast-growing", VC-backed\n'
    '- "mittelstand": established German mid-size company, often family-owned, traditional structure\n'
    '- "enterprise": large corporation (DAX, global player, > 2000 employees)\n'
    '- "public_sector": government or public institution (use when company_type is public_sector)\n'
    '- "unknown": cannot determine\n\n'
    "Strong signals for consulting/staffing:\n"
    '- "im Auftrag unseres Kunden" (on behalf of our client)\n'
    '- "für unseren Kunden suchen wir" (for our client we are searching)\n'
    '- "unser Mandant" (our client)\n'
    "- istPrivateArbeitsvermittlung: true\n"
    "- Company name contains Consulting, Solutions, Personalvermittlung, Recruiting\n\n"
    "industry — use a short English label. Prefer one of these canonical values when they fit:\n"
    + _CANONICAL_STR + "\n\n"
    "Use a concise custom label only when none of the above apply"
    ' (e.g. "Space Technology", "Smart Parking / IoT").'
    " Avoid compound labels like \"FinTech / Digital Banking Solutions\" —"
    " prefer the shortest accurate label.\n"
)


_VALID_TYPES = {"product", "consulting", "public_sector", "unknown"}


def _normalize(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("company_type") not in _VALID_TYPES:
        result["company_type"] = "product"
    return result


def _job_block(job_data: dict[str, Any], desc_limit: int = 3000) -> str:
    return (
        f"Company: {job_data.get('firma', '')}\n"
        f"Title: {job_data.get('stellenangebotsTitel', '')}\n"
        f"istPrivateArbeitsvermittlung: {job_data.get('istPrivateArbeitsvermittlung', False)}\n\n"
        f"Description:\n{job_data.get('stellenangebotsBeschreibung', '')[:desc_limit]}"
    )


def _parse_llm_text(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        logger.debug(f"LLM raw response (failed to parse):\n{text!r}")
        raise


def classify_job(job_data: dict[str, Any], api_key: str) -> dict[str, Any]:
    model = resolve_model("CLASSIFY_MODEL")
    text = llm_complete(
        [{"role": "user", "content": _job_block(job_data)}],
        system=SYSTEM_PROMPT,
        model=model,
        api_key=api_key,
        max_tokens=2048,
        fallback_model_var="CLASSIFY_FALLBACK_MODEL",
    )
    return _normalize(_parse_llm_text(text))


def classify_job_batch(jobs_data: list[dict[str, Any]], api_key: str) -> list[dict[str, Any]]:
    """Classify multiple companies in one LLM call. Returns results in the same order."""
    n = len(jobs_data)
    blocks = "\n\n".join(f"[{i+1}]\n{_job_block(job, desc_limit=1500)}" for i, job in enumerate(jobs_data))
    user_content = (
        f"Classify these {n} job listings. "
        f"Return a JSON array of exactly {n} objects in the same order.\n\n{blocks}"
    )
    model = resolve_model("CLASSIFY_MODEL")
    text = llm_complete(
        [{"role": "user", "content": user_content}],
        system=SYSTEM_PROMPT,
        model=model,
        api_key=api_key,
        max_tokens=2048 + 200 * n,
        fallback_model_var="CLASSIFY_FALLBACK_MODEL",
    )
    results = _parse_llm_text(text)
    if not isinstance(results, list) or len(results) != n:
        raise ValueError(f"Expected {n} results, got {len(results) if isinstance(results, list) else type(results).__name__}")
    return [_normalize(r) for r in results]


def print_summary(role_slug: str = DEFAULT_ROLE) -> None:
    from jobfit.db import get_session
    from jobfit.db.models import Classification as ClsModel

    with get_session() as session:
        rows = session.query(ClsModel).filter(ClsModel.role == role_slug).all()

    vals = [
        {"company_type": r.company_type, "company_stage": r.company_stage, "industry": r.industry}
        for r in rows
    ]
    product = sum(1 for v in vals if v.get("company_type") == "product")
    consulting = sum(1 for v in vals if v.get("company_type") == "consulting")
    public_sector = sum(1 for v in vals if v.get("company_type") == "public_sector")
    unknown = sum(1 for v in vals if v.get("company_type") == "unknown")

    stages: dict[str, int] = {}
    industries: dict[str, int] = {}
    for v in vals:
        if v.get("company_type") == "product":
            stage = v.get("company_stage", "unknown")
            stages[stage] = stages.get(stage, 0) + 1
            ind = v.get("industry", "unknown")
            industries[ind] = industries.get(ind, 0) + 1

    logger.info(
        f"Total classified: {len(vals)}"
        f"  (product: {product}, consulting: {consulting},"
        f" public_sector: {public_sector}, unknown: {unknown})"
    )

    if stages:
        for stage, count in sorted(stages.items(), key=lambda x: -x[1]):
            logger.info(f"  {stage:12} {count:>3}")

    if industries:
        logger.info("Top industries (product only):")
        for ind, count in sorted(industries.items(), key=lambda x: -x[1])[:10]:
            logger.info(f"  {ind:20} {count:>3}")

    registry = update_unmatched(role_slug)
    if registry:
        logger.warning(f"⚠  Unmatched industries → 'Other' ({len(registry)} unique):")
        for raw, entry in sorted(registry.items(), key=lambda x: -x[1]["count"]):
            logger.warning(f"  {entry['count']:>2}x  {raw}")


def audit(args: argparse.Namespace) -> None:
    """Show company_type inconsistencies and invalid values. No LLM calls."""
    from collections import defaultdict
    from jobfit.db import get_session
    from jobfit.db.models import Classification as ClsModel

    role: Role = getattr(args, "role_obj", ROLES[DEFAULT_ROLE])

    with get_session() as session:
        rows = session.query(ClsModel.firma, ClsModel.company_type, ClsModel.company_stage).filter(
            ClsModel.role == role.slug
        ).all()

    # Invalid enum values
    invalid = [r for r in rows if r.company_type not in _VALID_TYPES]
    if invalid:
        logger.warning(f"Invalid company_type values ({len(invalid)} records):")
        for r in sorted(invalid, key=lambda x: x.firma):
            logger.warning(f"  type={r.company_type!r}  stage={r.company_stage!r}  {r.firma}")
    else:
        logger.info("No invalid company_type values.")

    # Inconsistencies by company_type
    by_firma: dict[str, list] = defaultdict(list)
    for r in rows:
        by_firma[r.firma].append(r.company_type)

    inconsistent = []
    for firma, types in by_firma.items():
        unique = set(types)
        if len(unique) > 1:
            counts = {t: types.count(t) for t in unique}
            total = sum(counts.values())
            inconsistent.append((total, firma, counts))

    if not inconsistent:
        logger.info("No company_type inconsistencies.")
    else:
        logger.warning(f"\ncompany_type inconsistencies ({len(inconsistent)} companies):\n")
        for total, firma, counts in sorted(inconsistent, reverse=True):
            split = "  vs  ".join(f"{n}x {t}" for t, n in sorted(counts.items(), key=lambda x: -x[1]))
            logger.warning(f"  {total:>3}x  {split:<40}  {firma}")

    # Unmatched industries — refresh from current classifications + current normalize()
    registry = update_unmatched(role.slug)
    if registry:
        logger.warning(f"\n⚠  Unmatched industries → 'Other' ({len(registry)} unique):")
        for raw, entry in sorted(registry.items(), key=lambda x: -x[1]["count"]):
            logger.warning(f"  {entry['count']:>2}x  {raw}")
    else:
        logger.info("No unmatched industries.")



def _build_firma_cache(role_slug: str, min_count: int = 3) -> dict[str, dict]:
    """Return firms with >= min_count consistent classifications.

    Consistent means all existing records for that firma agree on
    company_type, company_stage, and industry.
    """
    from jobfit.db import get_session
    from jobfit.db.models import Classification as ClsModel
    from sqlalchemy import func
    from collections import defaultdict

    with get_session() as session:
        rows = (
            session.query(
                ClsModel.firma,
                ClsModel.company_type,
                ClsModel.company_stage,
                ClsModel.industry,
                func.count(ClsModel.refnr).label("n"),
            )
            .filter(ClsModel.role == role_slug)
            .group_by(ClsModel.firma, ClsModel.company_type, ClsModel.company_stage, ClsModel.industry)
            .all()
        )

    by_firma: dict[str, list] = defaultdict(list)
    for r in rows:
        by_firma[r.firma].append((r.company_type, r.company_stage, r.industry, r.n))

    cache: dict[str, dict] = {}
    for firma, variants in by_firma.items():
        total = sum(v[3] for v in variants)
        if total < min_count:
            continue
        unique_combos = {(v[0], v[1], v[2]) for v in variants}
        if len(unique_combos) == 1:
            ctype, cstage, industry = next(iter(unique_combos))
            cache[firma] = {"company_type": ctype, "company_stage": cstage, "industry": industry}

    return cache


def unclassified_count(role_slug: str) -> int:
    """Return number of jobs not yet classified for the given role."""
    from jobfit.db import get_session
    from jobfit.db.models import Job as JobModel, Classification as ClsModel

    with get_session() as session:
        return (
            session.query(JobModel)
            .outerjoin(ClsModel, JobModel.refnr == ClsModel.refnr)
            .filter(JobModel.role == role_slug, ClsModel.refnr.is_(None))
            .count()
        )


def run(args: argparse.Namespace) -> None:
    from jobfit.db import get_session
    from jobfit.db.models import Job as JobModel, Classification as ClsModel

    role: Role = getattr(args, "role_obj", ROLES[DEFAULT_ROLE])

    try:
        api_key = resolve_key()
    except RuntimeError as e:
        logger.error(str(e))
        sys.exit(1)

    with get_session() as session:
        already_done = session.query(ClsModel).filter(ClsModel.role == role.slug).count()
        unclassified = (
            session.query(JobModel)
            .outerjoin(ClsModel, JobModel.refnr == ClsModel.refnr)
            .filter(JobModel.role == role.slug, ClsModel.refnr.is_(None))
            .all()
        )

    remaining = len(unclassified)
    limit = getattr(args, "limit", None)
    jobs = unclassified[:limit] if limit is not None else unclassified
    to_process = len(jobs)

    logger.info(
        f"Dataset: {already_done + remaining}"
        f" | Classified: {already_done}"
        f" | Remaining: {remaining}"
        f" | Processing now: {to_process}"
    )

    if not jobs:
        logger.info("Nothing to classify.")
        print_summary(role.slug)
        logger.info("── classify audit ──────────────────────")
        audit(args)
        logger.info("── brands audit ────────────────────────")
        from jobfit import brands as _brands
        _brands.audit(args)
        return

    batch_size = int(os.environ.get("CLASSIFY_BATCH_SIZE", "10"))

    firma_cache = _build_firma_cache(role.slug)
    cached_count = sum(1 for job in jobs if (job.firma or "") in firma_cache)
    if cached_count:
        logger.info(f"Firma cache: {cached_count}/{to_process} jobs will skip LLM")

    # Phase 1: classify unique new companies in batches
    run_cache: dict[str, dict] = {}
    new_firma_jobs: dict[str, dict] = {}  # firma → one representative job_data
    for job_row in jobs:
        firma = job_row.firma or ""
        if firma not in firma_cache and firma not in new_firma_jobs:
            new_firma_jobs[firma] = {
                "stellenangebotsBeschreibung": job_row.beschreibung or "",
                "firma": firma,
                "stellenangebotsTitel": job_row.titel or "",
                "istPrivateArbeitsvermittlung": False,
            }

    unique_new = list(new_firma_jobs.items())
    dedup_savings = (to_process - cached_count) - len(unique_new)
    if dedup_savings > 0:
        logger.info(f"Intra-run dedup: {dedup_savings} jobs reuse result from same firma")

    if unique_new:
        logger.info(f"LLM: {len(unique_new)} unique companies → {(len(unique_new) + batch_size - 1) // batch_size} batches of {batch_size}")
        with tqdm(total=len(unique_new), unit="company", desc="LLM") as llm_bar:
            for i in range(0, len(unique_new), batch_size):
                batch = unique_new[i:i + batch_size]
                batch_firmas = [item[0] for item in batch]
                batch_jobs = [item[1] for item in batch]
                try:
                    results = classify_job_batch(batch_jobs, api_key)
                    for firma, result in zip(batch_firmas, results):
                        run_cache[firma] = result
                except _openai.RateLimitError as e:
                    logger.error(f"Rate limit hit on batch {i // batch_size + 1} — stopping to preserve daily quota")
                    raise
                except Exception as e:
                    logger.warning(f"Batch {i // batch_size + 1} failed ({e}), falling back to individual calls")
                    for firma, job_data in batch:
                        try:
                            run_cache[firma] = classify_job(job_data, api_key)
                        except _openai.RateLimitError:
                            logger.error("Rate limit hit during fallback — stopping to preserve daily quota")
                            raise
                        except Exception as e2:
                            logger.error(f"  {firma}: {e2}")
                llm_bar.update(len(batch))

    # Phase 2: write classifications to DB
    with tqdm(total=to_process, unit="job", desc="Write") as bar:
        for job_row in jobs:
            try:
                firma = job_row.firma or ""
                result = firma_cache.get(firma) or run_cache.get(firma)
                if result is None:
                    logger.error(f"{job_row.refnr}: no classification for firma={firma!r}, skipping")
                    continue

                cls = ClsModel(
                    refnr=job_row.refnr,
                    role=role.slug,
                    company_type=result.get("company_type"),
                    company_stage=result.get("company_stage"),
                    industry=result.get("industry"),
                    firma=firma,
                    titel=job_row.titel or "",
                    ort=job_row.ort_raw or "",
                    region="",
                )
                with get_session() as session:
                    session.add(cls)

                bar.set_postfix_str(f"{result.get('company_type', '?')}/{result.get('company_stage', '?')}  {(result.get('industry') or '')[:20]}")
            except Exception as e:
                logger.error(f"{job_row.refnr}  ERROR: {e}")
            finally:
                bar.update(1)

    print_summary(role.slug)
    logger.info("── classify audit ──────────────────────")
    audit(args)
    logger.info("── enrich audit ────────────────────────")
    from jobfit import enrich as _enrich
    _enrich.audit(role)
    logger.info("── brands audit ────────────────────────")
    from jobfit import brands as _brands
    _brands.audit(args)
