#!/usr/bin/env python3
"""Discover tech terms in job descriptions not covered by current SKILLS patterns.

Usage:
    python scripts/skill_audit.py               # all product companies
    python scripts/skill_audit.py --segment startup
    python scripts/skill_audit.py --segment mittelstand
    python scripts/skill_audit.py --segment enterprise
    python scripts/skill_audit.py --top 50      # show more candidates
    python scripts/skill_audit.py --min-count 5 # higher threshold
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jobfit.config import CLASSIFICATIONS_FILE, JOBS_DIR, SKILLS

# ── Tech term extraction ──────────────────────────────────────────────────────

# Matches CamelCase (ArgoCD, GitLab), ACRONYMS (RBAC, SRE), mixed (K8s, S3)
_TERM_RE = re.compile(
    r"\b(?:"
    r"[A-Z][a-z]{1,}(?:[A-Z][a-zA-Z0-9]*)+|"   # CamelCase: ArgoCD, OpenShift
    r"[A-Z]{3,10}(?:\.[A-Z]{2,6})*|"             # ACRONYM ≥3: AWS, RBAC (not WIR/YOU)
    r"[A-Za-z]+[0-9]+[A-Za-z0-9]*"               # alphanum: K8s, S3, EKS2
    r")\b"
)

# Generic phrases / non-tech words to filter out
_IGNORE = {
    # Corporate / legal
    "GmbH", "AG", "KG", "SE", "GbR", "AdöR", "VVaG", "LLC", "Ltd", "Inc",
    # HR / job posting
    "Senior", "Junior", "Lead", "Head", "Staff", "Principal",
    "Manager", "Engineer", "Developer", "Architect", "Consultant",
    "Analyst", "Specialist", "Director", "Officer", "Owner",
    "DevOps", "Backend", "Frontend", "FullStack", "OnSite", "Remote",
    "SaaS", "PaaS", "IaaS", "BaaS",
    "StartUp", "ScaleUp",
    # Benefits / perks
    "JobRad", "EGYM", "BAV", "BGM",
    # Locations / regions
    "Berlin", "Munich", "Hamburg", "Frankfurt", "Stuttgart", "Cologne",
    "Dortmund", "Leipzig", "Dresden", "Hannover", "Nuremberg",
    "Germany", "Europe", "DACH", "EMEA", "APAC",
    "Homeoffice", "HomeOffice",
    # Generic tech acronyms (not skills themselves)
    "API", "REST", "SOAP", "JSON", "XML", "YAML", "HTML", "CSS",
    "HTTP", "HTTPS", "TCP", "UDP", "DNS", "SSL", "TLS", "VPN",
    "SQL", "NoSQL", "CRUD", "ORM",
    "CI", "CD", "VCS", "SCM", "IaC",
    "OS", "VM", "GPU", "CPU", "RAM", "SSD",
    "UI", "UX", "GUI", "CLI", "SDK", "IDE",
    "EOF", "PDF", "CSV", "RSS",
    # Business / process
    "ISO", "ERP", "CRM", "ELK", "SAP",  # SAP kept generic; add back if relevant
    "B2B", "B2C", "B2G",
    "MVP", "OKR", "KPI", "SLA", "SLO", "SLI", "RTO", "RPO",
    "ITIL", "ITSM", "GDPR", "DSGVO",
    # Roles / org
    "CTO", "CEO", "CIO", "CISO", "CDO", "CPO",
    "QA", "PO", "PM",
    # Social / marketing
    "LinkedIn", "GitHub",  # GitHub is a platform but too generic as a skill
    "YouTube", "Twitter", "Slack",
    # Common English words written in ALL-CAPS in job postings
    "YOU", "YOUR", "THE", "AND", "FOR", "WITH", "OUR", "ARE", "HAVE",
    "WHAT", "THAT", "THIS", "WILL", "ABOUT", "TEAM", "WORK", "MORE",
    "JOIN", "ALSO", "FIND", "HELP", "MAKE", "TAKE", "GIVE", "COME",
    # Common German words written in ALL-CAPS
    "WIR", "SIE", "DAS", "DIE", "DER", "DEN", "DEM", "EIN", "EINE",
    "MIT", "UND", "ALS", "AUF", "BEI", "FÜR", "VON", "ZUR", "ZUM",
    "DEIN", "DEINE", "DEINEN", "UNSER", "UNSERE", "SUCHEN", "BIETEN",
    "HABEN", "WERDEN", "KÖNNEN", "BIETET", "GESTALTEN", "BIST", "BRINGST",
    "BRING", "AUFGABEN", "SHINE", "WARUM", "KOMM", "JETZT", "MEHR",
    "MACH", "DANN", "ODER", "AUCH", "NOCH", "WENN", "ALLE",
    # Company names / brands (non-tech)
    "PreZero", "REWE", "MacBooks", "MacBook", "ThinkPads", "WomEngineers",
    # Networking concepts (not actionable skills)
    "LAN", "WAN", "BGP", "DHCP", "VLAN",
    # Finance / non-tech
    "EUR", "ETF", "PKW",
    # Generic IT concepts (not skills)
    "ETL", "SSO", "WAF", "SIEM", "IoT", "M365", "SharePoint",
    "SOC", "MFA", "OIDC", "JIRA", "MacOS",
    # Cloud provider names (not services)
    "HashiCorp", "OVH", "IONOS",
    # Certifications (not skills themselves)
    "CKA", "CKAD", "CISSP", "CCNA", "CNCF",
    # Languages already in SKILLS
    "Python", "Java", "Rust", "Ruby", "Scala",
    "TypeScript", "JavaScript", "PowerShell", "Bash",
    "Groovy", "PHP", "Swift", "Kotlin", "Golang",
    # OS / distros already in SKILLS
    "Linux", "Windows", "macOS", "Android", "iOS",
    "RHEL", "Ubuntu", "Debian", "CentOS", "Fedora",
}

# Compile all existing SKILLS patterns into one combined regex for fast matching
_SKILLS_RE = re.compile(
    "|".join(f"(?:{pat})" for _, pat in SKILLS),
    re.IGNORECASE,
)


def _covered_by_skills(term: str) -> bool:
    return bool(_SKILLS_RE.search(term))


def _extract_terms(text: str) -> list[str]:
    return [
        m
        for m in _TERM_RE.findall(text)
        if m not in _IGNORE
        and len(m) >= 3
        and not _covered_by_skills(m)
    ]


# ── Load jobs ─────────────────────────────────────────────────────────────────

def load_descriptions(segment: str | None) -> list[str]:
    classifications = json.loads(CLASSIFICATIONS_FILE.read_text())
    texts = []
    for refnr, meta in classifications.items():
        if meta.get("_closed"):
            continue
        if meta.get("company_type") != "product":
            continue
        if segment and meta.get("company_stage") != segment:
            continue
        f = JOBS_DIR / f"{refnr}.json"
        if f.exists():
            job = json.loads(f.read_text())
            desc = job.get("stellenangebotsBeschreibung", "")
            if desc:
                texts.append(desc)
    return texts


# ── Current SKILLS frequency ──────────────────────────────────────────────────

def show_skills_frequency(texts: list[str], segment: str | None) -> None:
    label = segment or "all product"
    print(f"\n{'─'*60}")
    print(f"SKILLS frequency  [{label}, n={len(texts)}]")
    print(f"{'─'*60}")

    results = []
    for name, pattern in SKILLS:
        rx = re.compile(pattern, re.IGNORECASE)
        n = sum(1 for t in texts if rx.search(t))
        results.append((n, name))

    dead = [(n, name) for n, name in results if n == 0]
    rare = [(n, name) for n, name in results if 0 < n < 10]

    for n, name in sorted(results, reverse=True):
        pct = n * 100 // len(texts) if texts else 0
        bar = "█" * (pct // 3) + "░" * (33 - pct // 3)
        print(f"  {n:4} ({pct:3}%)  {bar}  {name}")

    if dead:
        print(f"\n  ⚠  Dead (0 mentions): {', '.join(name for _, name in dead)}")
    if rare:
        print(f"  ↓  Rare (<10): {', '.join(name for _, name in rare)}")


# ── Discover uncovered terms ──────────────────────────────────────────────────

def show_candidates(texts: list[str], top: int, min_count: int) -> None:
    print(f"\n{'─'*60}")
    print(f"Uncovered tech terms (not matched by any SKILLS pattern)")
    print(f"{'─'*60}")

    # Count per-document (not total occurrences) to avoid spam from one job
    doc_counter: Counter[str] = Counter()
    for text in texts:
        terms = set(_extract_terms(text))
        doc_counter.update(terms)

    candidates = [
        (count, term)
        for term, count in doc_counter.items()
        if count >= min_count
    ]
    candidates.sort(reverse=True)

    print(f"  {'count':>5}  {'%':>4}  term")
    for count, term in candidates[:top]:
        pct = count * 100 // len(texts) if texts else 0
        print(f"  {count:>5}  {pct:>3}%  {term}")

    print(f"\n  Total unique uncovered terms ≥{min_count}: {len(candidates)}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segment", choices=["startup", "mittelstand", "enterprise"],
                        help="Filter by company stage")
    parser.add_argument("--top", type=int, default=40,
                        help="How many candidate terms to show (default: 40)")
    parser.add_argument("--min-count", type=int, default=5,
                        help="Minimum doc count for candidates (default: 5)")
    parser.add_argument("--freq", action="store_true",
                        help="Show current SKILLS frequency table")
    parser.add_argument("--discover", action="store_true",
                        help="Show uncovered term candidates")
    args = parser.parse_args()

    # Default: show both
    show_freq = args.freq or not args.discover
    show_disc = args.discover or not args.freq

    texts = load_descriptions(args.segment)
    if not texts:
        print("No job descriptions found.", file=sys.stderr)
        sys.exit(1)

    if show_freq:
        show_skills_frequency(texts, args.segment)
    if show_disc:
        show_candidates(texts, args.top, args.min_count)


if __name__ == "__main__":
    main()
