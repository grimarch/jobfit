"""All constants, paths, REGION_NAMES, and configuration for jobfit."""

import os
import re
from pathlib import Path

from jobfit.roles import DEFAULT_ROLE, ROLES

# ── Paths ─────────────────────────────────────────────────────────────────────

def default_data_dir() -> Path:
    """Default data root: ./data (relative to CWD). Override with JOBFIT_DATA_DIR."""
    return Path("data")


def _resolve_data_dir() -> Path:
    raw = os.environ.get("JOBFIT_DATA_DIR", "").strip()
    path = Path(raw).expanduser() if raw else default_data_dir()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


DATA_DIR = _resolve_data_dir()


def _resolve_subdir(env_var: str, default: Path) -> Path:
    raw = os.environ.get(env_var, "").strip()
    path = Path(raw).expanduser() if raw else default
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


JOBS_DATA_DIR = _resolve_subdir("JOBFIT_JOBS_DATA_DIR", DATA_DIR / "jobs")
USER_DATA_DIR = _resolve_subdir("JOBFIT_USER_DATA_DIR", DATA_DIR / "user")
RAW_DIR = JOBS_DATA_DIR / "raw"


def _resolve_reports_dir() -> Path:
    raw = os.environ.get("JOBFIT_REPORTS_DIR", "").strip()
    path = Path(raw).expanduser() if raw else Path("dashboards")
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


REPORTS_DIR = _resolve_reports_dir()
_data_dir_logged = False


def log_data_dir() -> None:
    """Log resolved personal data root once per process."""
    global _data_dir_logged
    if _data_dir_logged:
        return
    _data_dir_logged = True
    _log_data_dir(
        DATA_DIR.resolve(),
        role_input_dir(DEFAULT_ROLE).resolve(),
    )


def _log_data_dir(data_dir: Path, role_input: Path) -> None:
    from loguru import logger

    logger.info(
        "Using data directory: {} (role input example: {})",
        data_dir,
        role_input,
    )


def log_reports_dir() -> None:
    from loguru import logger

    logger.info("Using reports directory: {}", REPORTS_DIR.resolve())


def ensure_raw_dir() -> None:
    """Create data/jobs/raw/ if missing (gitignored, may not exist on fresh clone)."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)


SOFTGARDEN_COMPANIES_FILE = JOBS_DATA_DIR / "softgarden_companies.csv"


def role_input_dir(role_slug: str = DEFAULT_ROLE) -> Path:
    """User-provided artifacts for a role: CV source, photo, prompts.

    Future multi-user layout: DATA_DIR / "user" / user_id / role_slug / "input".
    """
    return USER_DATA_DIR / role_slug / "input"


def role_output_dir(role_slug: str = DEFAULT_ROLE) -> Path:
    """Generated artifacts for a role: cv_profile.json, tailored CVs.

    Future multi-user layout: DATA_DIR / "user" / user_id / role_slug / "output".
    """
    return USER_DATA_DIR / role_slug / "output"


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


