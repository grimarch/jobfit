"""All constants, paths, REGION_NAMES, and configuration for jobfit."""

import re
from pathlib import Path

from loguru import logger
from jobfit.roles import DEFAULT_ROLE, ROLES

# ── Paths ─────────────────────────────────────────────────────────────────────

DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"
REPORTS_DIR = Path("dashboards")


def ensure_raw_dir() -> None:
    """Create data/raw/ if missing (gitignored, may not exist on fresh clone)."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)


SOFTGARDEN_COMPANIES_FILE = DATA_DIR / "softgarden_companies.csv"


def role_input_dir(role_slug: str = DEFAULT_ROLE) -> Path:
    """User-provided artifacts for a role: CV source, photo, prompts.

    Future multi-user layout: DATA_DIR / user_id / role_slug / "input".
    """
    return DATA_DIR / role_slug / "input"


def role_output_dir(role_slug: str = DEFAULT_ROLE) -> Path:
    """Generated artifacts for a role: cv_profile.json, tailored CVs.

    Future multi-user layout: DATA_DIR / user_id / role_slug / "output".
    """
    return DATA_DIR / role_slug / "output"


# ── Job fetching ───────────────────────────────────────────────────────────────

ATS_SOURCES = [
    "ashby",
    "eures",
    "greenhouse",
    "join_com",
    "lever",
    "personio",
    "phenom",
    "recruitee",
    "smartrecruiters",
    "successfactors",
    "welcometothejungle",
    "workable",
    "workday",
]

# Legacy alias — use role.title_re in new code
DEVOPS_RE = ROLES[DEFAULT_ROLE].title_re

DE_RE = re.compile(r"\bGermany\b|\bDeutschland\b", re.IGNORECASE)

DE_CITIES_RE = re.compile(
    r"\b(Berlin|Munich|München|Hamburg|Frankfurt|Cologne|Köln|Stuttgart|"
    r"Düsseldorf|Dusseldorf|Nuremberg|Nürnberg|Leipzig|Dresden|"
    r"Hannover|Hanover|Bonn|Mannheim|Augsburg|Wiesbaden|Karlsruhe|"
    r"Freiburg|Münster|Dortmund|Essen|Duisburg|Bremen|Bochum|"
    r"Bielefeld|Aachen|Heidelberg|Potsdam|Rostock)\b",
    re.IGNORECASE,
)

# Legacy alias — use role.skills in new code
SKILLS = ROLES[DEFAULT_ROLE].skills

# ── Geography ─────────────────────────────────────────────────────────────────

REGION_NAMES: dict[str, str] = {
    "BADEN_WUERTTEMBERG": "Baden-Württemberg",
    "BAYERN": "Bayern",
    "BERLIN": "Berlin",
    "BRANDENBURG": "Brandenburg",
    "BREMEN": "Bremen",
    "HAMBURG": "Hamburg",
    "HESSEN": "Hessen",
    "MECKLENBURG_VORPOMMERN": "Mecklenburg-Vorpommern",
    "NIEDERSACHSEN": "Niedersachsen",
    "NORDRHEIN_WESTFALEN": "Nordrhein-Westfalen",
    "RHEINLAND_PFALZ": "Rheinland-Pfalz",
    "SAARLAND": "Saarland",
    "SACHSEN": "Sachsen",
    "SACHSEN_ANHALT": "Sachsen-Anhalt",
    "SCHLESWIG_HOLSTEIN": "Schleswig-Holstein",
    "THUERINGEN": "Thüringen",
}

# ── Stages ────────────────────────────────────────────────────────────────────

STAGES = ["startup", "mittelstand", "enterprise"]

# ── CV analysis settings (from compare_cv.py) ─────────────────────────────────
# Personal preferences (stage weighting, coverage threshold, senior-title exclusion)
# live in data/{role}/input/scoring.yaml — see jobfit.scoring_config.

TOP_JOBS = 10
MIN_MARKET_PCT = 5

VIEW_CONFIGS: list[tuple[str, str, list[str]]] = [
    ("sm", "Startup + Mittelstand", ["startup", "mittelstand"]),
    ("startup", "Startup", ["startup"]),
    ("mittelstand", "Mittelstand", ["mittelstand"]),
    ("enterprise", "Enterprise", ["enterprise"]),
]
DEFAULT_VIEW = "sm"


