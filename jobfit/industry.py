"""Industry taxonomy and normalization for job classifications."""

from __future__ import annotations

from datetime import date
from typing import Any

# ── Canonical list (for system prompt in classify.py) ─────────────────────────

CANONICAL: list[str] = [
    "FinTech",
    "Insurance",
    "Banking",
    "HealthTech / MedTech",
    "Defense & Aerospace",
    "Energy / CleanTech",
    "Automotive",
    "Telecom",
    "Mobility",
    "Gaming / Media",
    "Logistics",
    "eCommerce / Retail",
    "AI / ML",
    "Cybersecurity",
    "EdTech",
    "Manufacturing",
    "Public Sector",
    "IT Services / B2B",
    "SaaS / Cloud",
    "Real Estate / PropTech",
    "Other",
]

# ── Taxonomy (pattern matching, first match wins) ─────────────────────────────
# Rules:
#   - Specific/domain patterns come before generic ones.
#   - "SaaS / Cloud" is the catch-all for pure-tech companies without a clear domain.
#   - InsurTech is merged into Insurance.
#   - Patterns are matched against lowercase raw value via substring search.

_TAXONOMY: list[tuple[str, list[str]]] = [
    ("FinTech",             ["fintech", "credit rating"]),
    ("Insurance",           ["insurance", "insurtech"]),
    ("Banking",             ["banking", "financial services", "financial technology"]),
    ("HealthTech / MedTech", ["healthtech", "health tech", "medtech", "healthcare",
                               "medical", "biotech", "biopharma", "pharma", "life science"]),
    ("Defense & Aerospace", ["defense", "defence", "aerospace", "space tech", "satellite"]),
    ("Energy / CleanTech",  ["energy", "cleantech", "renewable", "ev charging", "electric vehicle",
                              "environmental services", "waste management"]),
    ("Automotive",          ["automotive"]),
    ("Telecom",             ["telecom", "telecommunications"]),
    ("Mobility",            ["mobility", "maas", "aviation", "hospitality", "travel tech"]),
    ("Gaming / Media",      ["gaming", "media", "streaming"]),
    ("Logistics",           ["logistics", "logtech", "supply chain"]),
    ("eCommerce / Retail",  ["ecommerce", "retail"]),
    ("AI / ML",             ["ai/", "/ai", " ai", "ai ", "machine learning", "robotics",
                              "generative ai", "computer vision", "neuromorphic", "quantum"]),
    ("Cybersecurity",       ["cybersecurity", "cyber security", "it security", "network security",
                              "security technology", "security systems", "security app",
                              "pki", "digital trust", "certificate services", "content governance", "security /"]),
    ("EdTech",              ["edtech", "ed tech", "education"]),
    ("Manufacturing",       ["manufacturing", "industrial", "electronics", "embedded",
                              "3d imaging", "spatial computing", "optics", "electron microscopy",
                              "hvac", "ventilation", "construction tech", "iot"]),
    ("Public Sector",       ["public sector", "government"]),
    ("IT Services / B2B",   ["it services", "it consulting", "managed services", "digital agency",
                              "b2b software", "engineering consulting", "design agency"]),
    ("SaaS / Cloud",        ["saas", "cloud", "software", "platform",
                              "it infrastructure", "hosting", "developer tools", "it solutions",
                              "adtech", "martech", "marketing tech"]),
    ("Real Estate / PropTech", ["real estate", "proptech", "prop tech"]),
]


def normalize(raw: str | None) -> str:
    """Map a raw industry label to a canonical category. Returns 'Other' if no match."""
    if not raw:
        return "Other"
    low = raw.lower()
    for canon, patterns in _TAXONOMY:
        if any(p in low for p in patterns):
            return canon
    return "Other"


# ── Unmatched industries registry ─────────────────────────────────────────────

def update_unmatched(role_slug: str) -> dict[str, Any]:
    """Rebuild unmatched_industries table from current product classifications.

    Scans all product company jobs, finds those whose industry normalizes to
    'Other', and upserts a registry row preserving first_seen and notes.

    Returns the updated registry dict.
    """
    from jobfit.db import get_session
    from jobfit.db.models import Classification as ClsModel
    from jobfit.db.models import UnmatchedIndustry

    today = date.today().isoformat()

    with get_session() as session:
        existing = {
            row.industry: {"first_seen": row.first_seen, "notes": row.notes}
            for row in session.query(UnmatchedIndustry).filter(
                UnmatchedIndustry.role == role_slug
            ).all()
        }

        rows = session.query(ClsModel).filter(
            ClsModel.role == role_slug,
            ClsModel.company_type == "product",
        ).all()

        fresh: dict[str, Any] = {}
        for row in rows:
            raw = row.industry or ""
            if normalize(raw) != "Other":
                continue
            firma = row.firma or "Unknown"
            if raw not in fresh:
                fresh[raw] = {
                    "count": 0,
                    "first_seen": existing.get(raw, {}).get("first_seen", today),
                    "companies": [],
                    "notes": existing.get(raw, {}).get("notes", ""),
                }
            fresh[raw]["count"] += 1
            if firma not in fresh[raw]["companies"]:
                fresh[raw]["companies"].append(firma)

        session.query(UnmatchedIndustry).filter(UnmatchedIndustry.role == role_slug).delete()
        for industry, entry in fresh.items():
            session.add(UnmatchedIndustry(
                role=role_slug,
                industry=industry,
                first_seen=entry["first_seen"],
                notes=entry["notes"],
            ))

    return fresh
