"""Target company tiering dashboard (Dreamjob / CV Builder / Easy Win / Skip)."""

import re
from collections import defaultdict
from typing import Any

import plotly.graph_objects as go
from loguru import logger

from jobfit.config import REPORTS_DIR
from jobfit.cv.io import cv_read, load_cv_profile
from jobfit.dashboards._render import (
    _DE_STYLE,
    _MODE_STYLE,
    _STAGE_STYLE,
    ensure_plotly_js,
    job_url,
    page_shell,
    render_template,
)
from jobfit.dashboards.scoring import norm_firma, score, skills_from_text, sort_key, tier
from jobfit.industry import normalize
from jobfit.roles import DEFAULT_ROLE, ROLES, Role
from jobfit.scoring_config import ScoringConfig, load_scoring_config

OUTPUT_HTML = REPORTS_DIR / "target_companies.html"

_NUTS1_DE: dict[str, str] = {
    "DE1": "Baden-Württ.", "DE2": "Bayern",         "DE3": "Berlin",
    "DE4": "Brandenburg",  "DE5": "Bremen",         "DE6": "Hamburg",
    "DE7": "Hessen",       "DE8": "Mecklenburg-VP", "DE9": "Niedersachsen",
    "DEA": "NRW",          "DEB": "Rheinland-Pf.",  "DEC": "Saarland",
    "DED": "Sachsen",      "DEE": "Sachsen-Anh.",   "DEF": "Schleswig-H.",
    "DEG": "Thüringen",
}
_NUTS_PAT     = re.compile(r"^[A-Z]{2}\s*\(([^)]+)\)$")
_STREET_RE    = re.compile(r"\b(?:straße|strasse|str\.\s*\d|allee|damm|ufer)\b", re.IGNORECASE)
_POSTAL_CITY  = re.compile(r"\b\d{4,5}\s+([A-ZÄÖÜ][^\s,]{2,})")
_REMOTE_STRIP = re.compile(r"\s*\([^)]*\bremote\b[^)]*\)|,?\s*\bremote\b[^,;]*", re.IGNORECASE)
_ORT_COUNTRY  = re.compile(
    r"^(?:germany|deutschland|österreich|austria|schweiz|switzerland|"
    r"netherlands|niederlande|belgien|belgium|france|frankreich|"
    r"ireland|uk|spain|poland|polska|italy|italia|finland|finnland|"
    r"sweden|schweden|norway|norwegen|denmark|dänemark|portugal|"
    r"czechia|czech\s+republic|tschechien|hungary|ungarn|romania|"
    r"bulgaria|croatia|slovakia|slovenia|estonia|latvia|lithuania|"
    r"luxembourg|luxemburg|[a-z]{2}\d+|\d{4,5})$",
    re.IGNORECASE,
)
_ORT_STATE    = re.compile(
    r"^(?:Bayern|Bavaria|Baden-Württemberg|Brandenburg|Bremen|Hamburg|Hessen|"
    r"Mecklenburg-Vorpommern|Niedersachsen|Nordrhein-Westfalen|Rheinland-Pfalz|"
    r"Saarland|Sachsen|Sachsen-Anhalt|Schleswig-Holstein|Thüringen|"
    r"Mittelfranken|Oberbayern|Schwaben|Unterfranken|Oberfranken|Oberpfalz|"
    r"Niederbayern|North\s+Rhine.Westphalia|Lower\s+Saxony|Saxony|"
    r"Metropolregion\s+\S+)$",
    re.IGNORECASE,
)
_ORT_MODE     = re.compile(
    r"^(?:remote[^,]*|hybrid[^,]*|office|mobile\s+work|trellis\s+\S+)$",
    re.IGNORECASE,
)
_DE_BARE_COUNTRY = re.compile(r"^(?:germany|deutschland)$", re.IGNORECASE)
_DE_CITIES_HINT = re.compile(
    r"\b(?:germany|deutschland|berlin|münchen|munich|hamburg|frankfurt|köln|cologne|"
    r"düsseldorf|stuttgart|dortmund|hannover|nürnberg|leipzig|bremen|bonn)\b",
    re.IGNORECASE,
)


def _first_city(parts: list[str]) -> str:
    tokens = [p.strip() for p in parts if len(p.strip()) >= 3]
    # Pass 1: not country, state, or mode
    for t in tokens:
        if not _ORT_COUNTRY.match(t) and not _ORT_STATE.match(t) and not _ORT_MODE.match(t):
            return t
    # Pass 2: allow states (but not countries or modes)
    for t in tokens:
        if not _ORT_COUNTRY.match(t) and not _ORT_MODE.match(t):
            return t
    return tokens[0] if tokens else ""


def _clean_ort(ort: str) -> str:
    ort = ort.strip()
    if not ort or re.match(r"^[-\s,;]+$", ort):
        return ""

    # 1. NUTS codes: "DE (DE212, DEA)" → "Bayern" / "NRW +2"
    m = _NUTS_PAT.match(ort)
    if m:
        codes  = [c.strip() for c in m.group(1).split(",")]
        states = list(dict.fromkeys(_NUTS1_DE[c[:3]] for c in codes if c[:3] in _NUTS1_DE))
        if states:
            return states[0] + (f" +{len(states) - 1}" if len(states) > 1 else "")
        return ort[:20]

    # 2. Semicolon multi-location → prefer German city segment
    if ";" in ort:
        segs = [s.strip() for s in ort.split(";")]
        de   = [s for s in segs if _DE_CITIES_HINT.search(s) or
                re.search(r"\b(?:germany|deutschland)\b", s, re.IGNORECASE)]
        ort  = (de[0] if de else segs[0])

    # 3. Strip "Remote …" mentions to expose physical location
    cleaned = _REMOTE_STRIP.sub("", ort).strip(", ")
    if cleaned:
        ort = cleaned

    # 4. Street address → extract city via postal code
    if _STREET_RE.search(ort):
        m2 = _POSTAL_CITY.search(ort)
        return m2.group(1)[:20] if m2 else "—"

    # 5. Split by common separators, prefer German city if present
    parts = re.split(r"[,/|\\]", ort)
    de_parts = [p.strip() for p in parts if _DE_CITIES_HINT.search(p)]
    if de_parts:
        de_city_parts = [p for p in de_parts if not _DE_BARE_COUNTRY.match(p)]
        best = de_city_parts[0] if de_city_parts else de_parts[0]
        city = re.sub(r"\s+or\b.*", "", best, flags=re.IGNORECASE).strip()
    else:
        city = _first_city(parts) or parts[0].strip()

    # Strip trailing parentheticals and ATS location labels
    city = re.sub(r"\s*\([^)]*\)", "", city).strip()
    city = re.sub(r"\s+(?:office|hub|campus|hq|headquarter\w*)$", "", city, flags=re.IGNORECASE).strip()

    return city[:24] or "—"

def _load_known_brands(role_slug: str) -> frozenset[str]:
    from jobfit.db import get_session
    from jobfit.db.models import KnownBrand

    with get_session() as session:
        rows = session.query(KnownBrand).filter(
            KnownBrand.role == role_slug,
            KnownBrand.is_known.is_(True),
        ).all()

    if not rows:
        logger.warning(
            f"No known brands in DB for role '{role_slug}' — "
            f"CV Builder tier disabled. Run: jobfit brands --role {role_slug}"
        )
        return frozenset()
    return frozenset(norm_firma(b.firma) for b in rows)

# ── Tier definitions ──────────────────────────────────────────────────────────

_TIERS: list[tuple[str, str, str, str]] = [
    # key,        label,         color,     bg
    ("starred",   "Starred",    "#f59e0b", "#fffbeb"),
    ("dreamjob",  "Dreamjob",   "#27a269", "#e4f5ed"),
    ("cvbuilder", "CV Builder", "#3b7dd8", "#ebf2ff"),
    ("easywin",   "Easy Win",   "#e07b20", "#fff4e6"),
    ("skip",      "Skip",       "#8896a8", "#f4f6fa"),
]

def _signed(n: int) -> str:
    return f"+{n}" if n >= 0 else f"−{abs(n)}"


def _stage_phrase(config: ScoringConfig) -> str:
    """'Startup', 'Startup or Mittelstand', … from dreamjob_stages — '' if unrestricted."""
    return " or ".join(s.capitalize() for s in config.dreamjob_stages)


def _dreamjob_clause(config: ScoringConfig) -> str:
    """Prose description of dreamjob's actual placement conditions — never hand-written,
    so it can't say 'startup' after dreamjob_stages no longer includes it."""
    stage_phrase = _stage_phrase(config)
    if stage_phrase and config.dreamjob_require_preferred_industry:
        return f"{stage_phrase} in a preferred industry"
    if stage_phrase:
        return stage_phrase
    if config.dreamjob_require_preferred_industry:
        return "Preferred industry"
    return "Highest-scoring jobs"


def _tier_overview(config: ScoringConfig) -> dict[str, tuple[str, str]]:
    """(summary shown in collapsed state, tier logic shown when expanded) — built from scoring.yaml."""
    t = config.tier_text
    industries = ", ".join(sorted(config.preferred_industries))
    stage_phrase = _stage_phrase(config)
    dreamjob_reqs = []
    if stage_phrase:
        dreamjob_reqs.append(f"<strong>{stage_phrase.lower()}</strong>")
    if config.dreamjob_require_preferred_industry:
        dreamjob_reqs.append(f"preferred industry: {industries}")
    coverage_pct = round(config.easywin_min_skill_coverage * 100)
    return {
        "starred": (t["starred"]["summary"], t["starred"]["criteria"]),
        "dreamjob": (
            f"{_dreamjob_clause(config)}. {t['dreamjob']['tagline']}",
            " · ".join(dreamjob_reqs) or "Highest-scoring jobs",
        ),
        "cvbuilder": (t["cvbuilder"]["summary"], t["cvbuilder"]["criteria"]),
        "easywin": (
            t["easywin"]["summary"],
            f"<strong>≥{coverage_pct}% skill coverage</strong> · "
            "job requires mostly tools you already have · "
            "not a dreamjob · no IT brand value · good for pipeline volume"
        ),
        "skip": (t["skip"]["summary"], t["skip"]["criteria"]),
    }


def _score_formula(config: ScoringConfig) -> str:
    ct, wm, sb = config.company_type_weights, config.work_mode_weights, config.company_stage_bonus
    return (
        f"product&nbsp;<strong>{_signed(ct.get('product', 0))}</strong> · "
        f"remote&nbsp;<strong>{_signed(wm.get('remote', 0))}</strong> · "
        f"startup&nbsp;<strong>{_signed(sb.get('startup', 0))}</strong> · "
        f"preferred&nbsp;industry&nbsp;<strong>{_signed(config.preferred_industry_bonus)}</strong> · "
        f"EN&nbsp;OK&nbsp;<strong>{_signed(config.english_ok_bonus)}</strong> · "
        f"salary&nbsp;≥{config.salary_bonus_threshold // 1000}k&nbsp;<strong>{_signed(config.salary_bonus_points)}</strong> · "
        f"mittelstand&nbsp;<strong>{_signed(sb.get('mittelstand', 0))}</strong> · "
        f"hybrid&nbsp;<strong>{_signed(wm.get('hybrid', 0))}</strong> · "
        f"no&nbsp;on-call&nbsp;<strong>{_signed(config.no_on_call_bonus)}</strong> · "
        f"onsite&nbsp;<strong>{_signed(wm.get('onsite', 0))}</strong> · "
        f"german&nbsp;C2&nbsp;<strong>{_signed(config.german_level_weights.get('C2', 0))}</strong> · "
        f"consulting/public&nbsp;<strong>{_signed(ct.get('consulting', 0))}</strong>"
    )


def _tier_scoring(config: ScoringConfig) -> dict[str, str]:
    t = config.tier_text
    stage_phrase = _stage_phrase(config)
    dreamjob_reqs = []
    if stage_phrase:
        dreamjob_reqs.append(stage_phrase.lower())
    if config.dreamjob_require_preferred_industry:
        dreamjob_reqs.append("preferred industry")
    dreamjob_cond = " AND ".join([f"score <strong>≥ {config.dreamjob_min_score}</strong>", *dreamjob_reqs])
    coverage_pct = round(config.easywin_min_skill_coverage * 100)
    return {
        "starred":   t["starred"]["scoring_note"],
        "dreamjob":  f"Placement: {dreamjob_cond}. Score reflects conditions — higher = stronger overall match.",
        "cvbuilder": t["cvbuilder"]["scoring_note"],
        "easywin":   f"Placement: skill coverage <strong>≥ {coverage_pct}%</strong>, or score <strong>≥ {config.easywin_fallback_min_score}</strong> fallback when no skill data. Score reflects conditions — use it to prioritise applications.",
        "skip":      t["skip"]["scoring_note"],
    }

_TIER_BADGE_STYLE: dict[str, tuple[str, str]] = {
    "dreamjob":  ("Dreamjob",   "background:#e4f5ed;color:#1a7a4e"),
    "cvbuilder": ("CV Builder", "background:#ebf2ff;color:#1e56b0"),
    "easywin":   ("Easy Win",   "background:#fff4e6;color:#b45309"),
    "skip":      ("Skip",       "background:#f4f6fa;color:#6b7a95"),
}
_TIER_SORT_KEY: dict[str, int] = {
    "dreamjob": 0, "cvbuilder": 1, "easywin": 2, "skip": 3,
}

_SOURCE_LABEL: dict[str, str] = {
    "":                   "BA",
    "eures":              "EURES",
    "join_com":           "Join",
    "successfactors":     "SF",
    "greenhouse":         "GH",
    "personio":           "Personio",
    "ashby":              "Ashby",
    "smartrecruiters":    "SR",
    "welcometothejungle": "WttJ",
    "phenom":             "Phenom",
    "workday":            "Workday",
    "recruitee":          "Recruitee",
    "lever":              "Lever",
    "workable":           "Workable",
    "softgarden":         "Softgarden",
    "germantechjobs":     "GTJ",
    "berlinstartupjobs":  "BSJ",
    "adzuna":             "Adzuna",
    "devopsjobs":         "DOJ",
    "devitjobs":          "DevIT",
    "landingjobs":        "Landing",
    "echojobs":           "Echo",
}

# ── Chart ─────────────────────────────────────────────────────────────────────

def _tier_chart(jobs: list[dict[str, Any]], tier_color: str) -> str:
    stages  = ["startup", "mittelstand", "enterprise", "unknown"]
    modes   = ["remote", "hybrid", "onsite"]
    colors  = {"remote": "#27a269", "hybrid": "#3b7dd8", "onsite": "#9c64a6"}
    labels  = {"startup": "Startup", "mittelstand": "Mittelstand",
                "enterprise": "Enterprise", "unknown": "Unknown"}

    counts: dict[str, dict[str, int]] = {s: {m: 0 for m in modes} for s in stages}
    for j in jobs:
        st = j.get("company_stage") or "unknown"
        md = j.get("work_mode") or "onsite"
        if st in counts and md in counts[st]:
            counts[st][md] += 1

    # drop stages with zero total
    active = [s for s in stages if sum(counts[s].values()) > 0]
    if not active:
        return ""

    traces = []
    for mode in modes:
        x = [counts[s][mode] for s in active]
        if any(x):
            traces.append(go.Bar(
                name=mode,
                y=[labels[s] for s in active],
                x=x,
                orientation="h",
                marker_color=colors[mode],
                hovertemplate="%{x} %{fullData.name}<extra></extra>",
            ))

    fig = go.Figure(data=traces)
    fig.update_layout(
        barmode="stack",
        height=40 + 36 * len(active),
        margin=dict(l=0, r=30, t=8, b=8),
        showlegend=True,
        legend=dict(orientation="h", y=1.18, x=0, font=dict(size=11)),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="system-ui,-apple-system,sans-serif", size=11),
        yaxis=dict(autorange="reversed"),
        xaxis=dict(gridcolor="#eef0f5", title=dict(text="vacancies", font=dict(size=10))),
    )
    return fig.to_html(
        include_plotlyjs=False,
        full_html=False,
        config=dict(displayModeBar=False),
    )


# ── Table ─────────────────────────────────────────────────────────────────────

_STAGE_SORT    = {"startup": 0, "mittelstand": 1, "enterprise": 2, "unknown": 3}
_MODE_SORT     = {"remote": 0, "hybrid": 1, "onsite": 2}
_LANG_SORT     = {"en": 0, "b1": 1, "b2": 2, "c1": 3, "c2": 4, "?": 5}
_SENIORITY_SORT = {"junior": 0, "mid": 1, "senior": 2, "lead": 3}

_SENIORITY_STYLE = {
    "junior": "background:#e8f4fd;color:#1a6fa8",
    "mid":    "background:#f4f6fa;color:#6b7a95",
    "senior": "background:#fff3e0;color:#b85c00",
    "lead":   "background:#f0ebff;color:#6a3fbf",
}
_BADGE_NEUTRAL = "background:#f4f6fa;color:#6b7a95"


def _jobs_table(jobs: list[dict[str, Any]], tier_color: str, table_id: str, show_tier: bool = False, role_slug: str = "") -> str:
    rows: list[dict[str, Any]] = []
    for j in jobs:
        score    = j["score"]
        refnr    = j["refnr"]
        firma    = j.get("firma", "—")
        titel    = j.get("titel", "—")
        if len(titel) > 55:
            titel = titel[:53] + "…"
        industry = normalize(j.get("industry"))
        stage    = j.get("company_stage") or "unknown"
        mode     = j.get("work_mode") or "—"
        eng      = j.get("english_ok", False)
        de       = j.get("german_level")
        sal_min  = j.get("salary_min")
        sal_max  = j.get("salary_max")
        url      = job_url(refnr, j.get("externe_url", ""))
        ort      = _clean_ort(j.get("ort") or "") or "—"
        seniority = j.get("seniority") or ""
        source   = j.get("source", "BA")

        if eng:
            lang_key, lang_text, lang_style = "en", "EN ✓", "background:#e4f5ed;color:#1a7a4e"
        elif de and de in _DE_STYLE:
            lang_key, lang_text, lang_style = de.lower(), f"DE {de}", _DE_STYLE[de]
        else:
            lang_key, lang_text, lang_style = "?", "DE ?", _BADGE_NEUTRAL

        fit_pct     = j.get("fit_pct", -1)
        fit_label   = j.get("fit_label", "—")
        if fit_pct < 0:
            fit_style = _BADGE_NEUTRAL
        elif fit_pct >= 80:
            fit_style = "background:#e4f5ed;color:#1a7a4e"
        elif fit_pct >= 50:
            fit_style = "background:#fff4e6;color:#b45309"
        else:
            fit_style = "background:#fdeaea;color:#b52a2a"

        sal = None
        if sal_max:
            lo = f"€{sal_min//1000}k–" if sal_min else ""
            sal = {"val": sal_max, "text": f"{lo}€{sal_max//1000}k"}

        tier_b = None
        if show_tier:
            original_tier = j.get("original_tier", "")
            tier_label, tier_style = _TIER_BADGE_STYLE.get(original_tier, ("—", _BADGE_NEUTRAL))
            tier_b = {"text": tier_label, "style": tier_style, "sort": _TIER_SORT_KEY.get(original_tier, 9)}

        rows.append({
            "score":          score,
            "tier_color":     tier_color,
            "firma":          firma,
            "firma_lower":    firma.lower(),
            "url":            url,
            "titel":          titel,
            "titel_lower":    titel.lower(),
            "industry":       industry,
            "industry_lower": industry.lower(),
            "stage_b":        {"text": stage,     "style": _STAGE_STYLE.get(stage, _BADGE_NEUTRAL),     "sort": _STAGE_SORT.get(stage, 3)},
            "mode_b":         {"text": mode,      "style": _MODE_STYLE.get(mode,   _BADGE_NEUTRAL),     "sort": _MODE_SORT.get(mode, 9)},
            "lang_b":         {"text": lang_text, "style": lang_style,                                   "sort": _LANG_SORT.get(lang_key, 6)},
            "ort":            ort,
            "ort_lower":      ort.lower(),
            "sen_b":          {"text": seniority, "style": _SENIORITY_STYLE.get(seniority, _BADGE_NEUTRAL), "sort": _SENIORITY_SORT.get(seniority, 9)} if seniority else None,
            "sal":            sal,
            "source_b":       {"text": source, "style": _BADGE_NEUTRAL},
            "source_lower":   source.lower(),
            "fit_b":          {"text": fit_label, "style": fit_style, "pct": fit_pct, "tooltip": j.get("fit_tooltip", "")},
            "refnr":          refnr,
            "tier_b":         tier_b,
        })

    off = 1 if show_tier else 0
    cols: list[dict[str, Any]] = [
        {"label": "Score",    "col": 0,      "is_num": True,  "center": True,  "plain": False},
    ]
    if show_tier:
        cols.append({"label": "Tier",     "col": 1,      "is_num": True,  "center": False, "plain": False})
    cols.extend([
        {"label": "Company",  "col": 1+off,  "is_num": False, "center": False, "plain": False},
        {"label": "Title",    "col": 2+off,  "is_num": False, "center": False, "plain": False},
        {"label": "Industry", "col": 3+off,  "is_num": False, "center": False, "plain": False},
        {"label": "Stage",    "col": 4+off,  "is_num": True,  "center": False, "plain": False},
        {"label": "Mode",     "col": 5+off,  "is_num": True,  "center": False, "plain": False},
        {"label": "Lang",     "col": 6+off,  "is_num": True,  "center": False, "plain": False},
        {"label": "Ort",      "col": 7+off,  "is_num": False, "center": False, "plain": False},
        {"label": "Seniority","col": 8+off,  "is_num": True,  "center": False, "plain": False},
        {"label": "Salary",   "col": 9+off,  "is_num": True,  "center": False, "plain": False},
        {"label": "Source",   "col": 10+off, "is_num": False, "center": False, "plain": False},
        {"label": "Fit",      "col": 11+off, "is_num": True,  "center": False, "plain": False},
        {"label": "★",        "col": 0,      "is_num": False, "center": False, "plain": True},
        {"label": "CV",       "col": 0,      "is_num": False, "center": False, "plain": True},
        {"label": "AS",       "col": 0,      "is_num": False, "center": False, "plain": True},
        {"label": "APRV",     "col": 0,      "is_num": False, "center": False, "plain": True},
        {"label": "PRV",      "col": 0,      "is_num": False, "center": False, "plain": True},
        {"label": "Read",     "col": 0,      "is_num": False, "center": False, "plain": True},
    ])

    return render_template("targets_table.html", rows=rows, cols=cols, table_id=table_id, role_slug=role_slug)


# ── Tier section ──────────────────────────────────────────────────────────────

def _tier_section(
    key: str,
    label: str,
    color: str,
    bg: str,
    jobs: list[dict[str, Any]],
    config: ScoringConfig,
    role_slug: str = "",
) -> str:
    n = len(jobs)
    chart_block = _tier_chart(jobs, color)
    table_html = _jobs_table(jobs, color, table_id=f"tbl-{key}", show_tier=(key == "starred"), role_slug=role_slug)
    tier_desc, tier_criteria = _tier_overview(config)[key]
    return render_template(
        "targets_tier_section.html",
        key=key,
        label=label,
        n=n,
        tier_desc=tier_desc,
        tier_criteria=tier_criteria,
        score_formula=_score_formula(config),
        tier_scoring=_tier_scoring(config)[key],
        chart_block=chart_block,
        table_html=table_html,
    )


# ── KPI row ───────────────────────────────────────────────────────────────────

def _kpi_row(tier_counts: dict[str, int], total: int) -> str:
    tiers = [
        {
            "key":   key,
            "label": label,
            "color": color,
            "n":     tier_counts.get(key, 0),
            "pct":   round(tier_counts.get(key, 0) / total * 100) if total else 0,
        }
        for key, label, color, _ in _TIERS
    ]
    return render_template("targets_kpi_row.html", tiers=tiers)


# ── Tabs ──────────────────────────────────────────────────────────────────────

def _tabs(tier_counts: dict[str, int]) -> str:
    tabs = [
        {"key": key, "label": label, "n": tier_counts.get(key, 0), "is_active": key == "starred"}
        for key, label, _, _ in _TIERS
    ]
    return render_template("targets_tabs.html", tabs=tabs)


# ── Data loading / tiering ────────────────────────────────────────────────────

def _load_user_skills(role: Role) -> frozenset[str]:
    profile = load_cv_profile(role.slug)
    if profile.get("skills"):
        logger.debug(f"user_skills: loaded {len(profile['skills'])} from cv_profile.json")
        return frozenset(profile["skills"])
    try:
        user_skills = skills_from_text(cv_read(role.slug), role.skills)
        logger.debug(f"user_skills: derived {len(user_skills)} from CV text (no cv_profile.json)")
        return user_skills
    except (FileNotFoundError, OSError):
        logger.warning("No CV file found — skill match will be empty. Run: jobfit cv extract <file>")
        return frozenset()


def _build_buckets(role: Role, config: ScoringConfig) -> dict[str, list[dict[str, Any]]]:
    """Load classified jobs and bucket them by tier."""
    from jobfit.db import cls_to_meta, get_session
    from jobfit.db.models import Classification as ClsModel
    from jobfit.db.models import Job as JobModel

    _compiled = [(name, re.compile(pat, re.IGNORECASE)) for name, pat in role.skills]
    cls: dict[str, Any] = {}
    _url_cache: dict[str, str] = {}
    _source_cache: dict[str, str] = {}
    _skills_cache: dict[str, frozenset[str]] = {}
    seen: set[tuple[str, str]] = set()

    with get_session() as session:
        db_rows = (
            session.query(ClsModel, JobModel)
            .join(JobModel)
            .filter(JobModel.role == role.slug, JobModel.closed_at.is_(None))
            .all()
        )
        for cls_row, job_row in db_rows:
            dedup_key = (cls_row.titel or "", cls_row.firma or "")
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            cls[job_row.refnr] = cls_to_meta(cls_row)
            if job_row.externe_url:
                _url_cache[job_row.refnr] = job_row.externe_url
            src = job_row.ats_source or ""
            _source_cache[job_row.refnr] = _SOURCE_LABEL.get(src, src or "BA")
            text = job_row.beschreibung or ""
            _skills_cache[job_row.refnr] = frozenset(
                name for name, pat in _compiled if pat.search(text)
            )

    known_brands = _load_known_brands(role.slug)
    user_skills = _load_user_skills(role)

    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for refnr, meta in cls.items():
        if meta.get("company_type") != "product":
            continue
        job = dict(meta)
        job["refnr"] = refnr
        job["score"] = score(meta, config)
        job["externe_url"] = _url_cache.get(refnr, "")
        job["source"] = _source_cache.get(refnr, "BA")
        job_skills = _skills_cache.get(refnr, frozenset())
        matched = job_skills & user_skills
        missing = job_skills - user_skills
        if job_skills:
            pct = round(len(matched) / len(job_skills) * 100)
            tooltip_parts = []
            if matched:
                tooltip_parts.append("✓ " + ", ".join(sorted(matched)))
            if missing:
                tooltip_parts.append("✗ missing: " + ", ".join(sorted(missing)))
            job["fit_pct"] = pct
            job["fit_label"] = f"{len(matched)}/{len(job_skills)}"
            job["fit_tooltip"] = "\n".join(tooltip_parts)
        else:
            job["fit_pct"] = -1
            job["fit_label"] = "—"
            job["fit_tooltip"] = ""
        buckets[tier(job["score"], meta, known_brands, job_skills, user_skills, config)].append(job)

    for jobs in buckets.values():
        jobs.sort(key=sort_key)

    with get_session() as session:
        starred_refnrs = frozenset(
            r[0] for r in session.query(ClsModel.refnr)
            .filter(ClsModel.starred_at.isnot(None))
            .all()
        )
    starred_jobs: list[dict[str, Any]] = []
    for tier_key, tier_jobs in buckets.items():
        for job in tier_jobs:
            if job["refnr"] in starred_refnrs:
                starred_jobs.append({**job, "original_tier": tier_key})
    starred_jobs.sort(key=sort_key)
    buckets["starred"] = starred_jobs
    return buckets


def tier_counts(role: Role | None = None) -> dict[str, int]:
    """Return job counts per tier for the targets dashboard."""
    if role is None:
        role = ROLES[DEFAULT_ROLE]
    config = load_scoring_config(role.slug)
    buckets = _build_buckets(role, config)
    return {k: len(buckets.get(k, [])) for k, *_ in _TIERS}


# ── Main render ───────────────────────────────────────────────────────────────

def render(role: "Role | None" = None) -> str:
    if role is None:
        role = ROLES[DEFAULT_ROLE]
    logger.info("Building target companies dashboard...")

    ensure_plotly_js(REPORTS_DIR)

    config = load_scoring_config(role.slug)
    buckets = _build_buckets(role, config)

    tier_counts_map = {k: len(buckets.get(k, [])) for k, *_ in _TIERS}
    total = sum(len(buckets.get(k, [])) for k, *_ in _TIERS if k != "starred")

    # Build page body
    body_parts: list[str] = []

    # Header
    body_parts.append(render_template("targets_header.html", total=total))

    # KPI row
    body_parts.append(_kpi_row(tier_counts_map, total))

    # Tabs
    body_parts.append(_tabs(tier_counts_map))

    # Tier sections
    for key, label, color, bg in _TIERS:
        jobs = buckets.get(key, [])
        body_parts.append(_tier_section(key, label, color, bg, jobs, config, role_slug=role.slug))

    # Initial view JS + table sort + read/unread + starred (rendered from template)
    extra_js = render_template("targets_extra.js", role_slug=role.slug)

    html = page_shell(
        title="Target Companies",
        body="".join(body_parts),
        active_page="targets",
        role_name=role.slug,
        extra_js=extra_js,
    )

    summary = "  /  ".join(
        f"{label} {tier_counts_map.get(key, 0)}" for key, label, _, _ in _TIERS
    )
    logger.info(f"Rendered dashboard  [{summary}]")
    return html


def save(role: "Role | None" = None) -> None:
    """Generate target companies dashboard and write to OUTPUT_HTML."""
    html = render(role)
    if html:
        OUTPUT_HTML.write_text(html, encoding="utf-8")
        logger.info(f"Saved: {OUTPUT_HTML}")
