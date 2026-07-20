"""Unit tests for jobfit/enrich.py detection functions."""

import pytest

from jobfit.enrich import (
    _ats_to_eur_year,
    _ba_salary,
    _is_english_description,
    detect_certifications,
    detect_education,
    detect_experience_years,
    detect_language,
    detect_on_call,
    detect_salary,
    detect_seniority,
    detect_work_mode,
)
from tests.conftest import ENGLISH_TEXT_SPARSE, GERMAN_TEXT_DENSE


# ── detect_work_mode ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("100% remote arbeiten",                        "remote"),
    ("100 % remote",                                "remote"),
    ("Remote First company",                        "remote"),
    ("ortsunabhängig tätig",                        "remote"),
    ("remote-first environment",                    "remote"),
    ("3 Tage Homeoffice pro Woche",                "hybrid"),
    ("Homeoffice möglich nach Einarbeitung",        "hybrid"),
    ("work from home 2 days per week",              "hybrid"),
    ("hybrid working model",                        "hybrid"),
    ("2 days in the office per week",               "hybrid"),
    ("Büro in München, Präsenz erforderlich",       "onsite"),
    ("",                                            "onsite"),
])
def test_detect_work_mode(text, expected):
    assert detect_work_mode(text) == expected


# ── detect_language ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,english_ok,german_level", [
    ("English is ok, no German needed",                     True,  None),
    ("no German language required",                         True,  None),
    ("German is not required",                              True,  None),
    ("working language is English",                         True,  None),
    ("we work in English",                                  True,  None),
    (ENGLISH_TEXT_SPARSE,                                   True,  None),
    ("muttersprachliche Deutschkenntnisse erforderlich",    False, "C2"),
    ("verhandlungssicheres Deutsch wird vorausgesetzt",     False, "C2"),
    ("Deutsch C2 Niveau",                                   False, "C2"),
    ("fließende Deutschkenntnisse",                         False, "C1"),
    ("sehr gute Deutschkenntnisse",                         False, "C1"),
    ("C1 Deutsch oder besser",                              False, "C1"),
    ("gute Deutschkenntnisse sind von Vorteil",             False, "B2"),
    ("Deutsch B2 Niveau",                                   False, "B2"),
    ("Grundkenntnisse Deutsch",                             False, "B1"),
    ("Deutsch B1 Kenntnisse",                               False, "B1"),
    # Explicit CEFR beats soft "verhandlungssicher" → C2
    (
        "Du sprichst Deutsch verhandlungssicher in Wort und Schrift (mindestens B1).",
        False,
        "B1",
    ),
    (
        "Deutschkenntnisse verhandlungssicher, mind. B2",
        False,
        "B2",
    ),
    # Alternatives: requirement floor is the lower level
    (
        "Sehr gute Sprachkenntnisse (in Wort und Schrift) sowie "
        "Kommunikationsfähigkeiten jeweils auf C1- oder C2-Niveau "
        "in Deutsch und Englisch",
        False,
        "C1",
    ),
    ("Deutschkenntnisse auf C1 oder C2 Niveau", False, "C1"),
    ("Deutschkenntnisse erforderlich",                      False, "required"),
    ("Deutsch zwingend vorausgesetzt",                      False, "required"),
    (GERMAN_TEXT_DENSE,                                     False, None),
])
def test_detect_language(text, english_ok, german_level):
    result_ok, result_level = detect_language(text)
    assert result_ok == english_ok
    assert result_level == german_level


def test_detect_language_english_description_density():
    assert _is_english_description(ENGLISH_TEXT_SPARSE) is True
    assert _is_english_description(GERMAN_TEXT_DENSE) is False


def test_detect_language_short_text_not_english():
    assert _is_english_description("Short text.") is False


# ── detect_on_call ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("Rufbereitschaft wird erwartet",           True),
    ("Bereitschaftsdienst am Wochenende",       True),
    ("on-call rotation required",               True),
    ("on call support",                         True),
    ("PagerDuty incidents response",            True),
    ("24/7 Bereitschaft notwendig",             True),
    ("incident response rotation",              True),
    ("normale Arbeitszeiten, kein Dienst",      False),
    ("",                                        False),
])
def test_detect_on_call(text, expected):
    assert detect_on_call(text) == expected


# ── detect_salary ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,sal_min,sal_max", [
    ("Gehalt: 70.000 – 90.000 EUR",            70000,  90000),
    ("zwischen 60.000 und 80.000 EUR",          80000,  None),   # "und" not a range separator → single match
    ("50.000 EUR brutto jährlich",              50000,  None),
    ("Jahresgehalt 80.000",                     80000,  None),
    ("75.000,– EUR",                            75000,  None),
    ("Gehalt: 65.000",                          65000,  None),
    ("4.415 bis 6.900 brutto im Monat",         52980,  82800),
    ("5.000 EUR",                               None,   None),   # < 20k
    ("500.000 EUR brutto",                      None,   None),   # > 300k
    ("Wettbewerbsfähige Vergütung",             None,   None),
    ("",                                        None,   None),
])
def test_detect_salary(text, sal_min, sal_max):
    result_min, result_max = detect_salary(text)
    assert result_min == sal_min
    assert result_max == sal_max


# ── _ats_to_eur_year ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw_val,currency,period,expected", [
    (75000,   "EUR",  "YEAR",  75000),
    (5000,    "EUR",  "MONTH", 60000),
    (30,      "EUR",  "HOUR",  30 * 1760),
    (65000,   None,   None,    65000),   # ≥20k → annual
    (4500,    None,   None,    54000),   # ≥1k → monthly × 12
    (500,     None,   None,    None),    # too small
    (0,       "EUR",  "YEAR",  None),
    (None,    "EUR",  "YEAR",  None),
    ("bad",   "EUR",  "YEAR",  None),
    (75000,   "USD",  "YEAR",  None),    # non-EUR
    (400000,  "EUR",  "YEAR",  None),    # > 300k
    (10000,   "EUR",  "YEAR",  None),    # < 20k
    (75000,   "EUR",  "WEEK",  None),    # unknown period
])
def test_ats_to_eur_year(raw_val, currency, period, expected):
    assert _ats_to_eur_year(raw_val, currency, period) == expected


# ── _ba_salary ────────────────────────────────────────────────────────────────

def test_ba_salary_jahresgehalt():
    job = {"gehaltsspanneVon": 50000, "gehaltsspanneBis": 70000, "verguetungsangabe": "JAHRESGEHALT"}
    assert _ba_salary(job) == (50000, 70000)


def test_ba_salary_no_bis():
    job = {"gehaltsspanneVon": 60000, "verguetungsangabe": "JAHRESGEHALT"}
    assert _ba_salary(job) == (60000, None)


def test_ba_salary_stundenlohn():
    job = {"gehaltsspanneVon": 30, "verguetungsangabe": "STUNDENLOHN"}
    lo, hi = _ba_salary(job)
    assert lo == 30 * 1760
    assert hi is None


def test_ba_salary_missing_field():
    assert _ba_salary({}) == (None, None)


def test_ba_salary_out_of_range():
    job = {"gehaltsspanneVon": 5000, "verguetungsangabe": "JAHRESGEHALT"}
    assert _ba_salary(job) == (None, None)


# ── detect_experience_years ───────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("mindestens 5 Jahre Berufserfahrung",      5),
    ("mind. 3 Jahre Erfahrung",                 3),
    ("3+ Jahre Berufserfahrung",                3),
    ("5 Jahre Erfahrung in DevOps",             5),
    ("5+ years of professional experience",     5),
    ("3–7 Jahre Berufserfahrung",               3),
    ("mehrjährige Erfahrung",                   3),
    ("mehrjährigen Berufserfahrung",            3),
    ("langjährige Berufserfahrung",             5),
    ("25 Jahre Erfahrung",                      None),  # > 20 → skip
    ("keine Angabe",                            None),
    ("",                                        None),
])
def test_detect_experience_years(text, expected):
    assert detect_experience_years(text) == expected


# ── detect_seniority ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("titel,years,expected", [
    ("Senior DevOps Engineer",      None, "senior"),
    ("Senior SRE",                  None, "senior"),
    ("Junior Cloud Engineer",       None, "junior"),
    ("Werkstudent DevOps",          None, "junior"),
    ("Lead Platform Engineer",      None, "lead"),
    ("Principal SRE",               None, "lead"),
    ("Head of Infrastructure",      None, "lead"),
    ("Staff Engineer",              None, "lead"),
    ("DevOps Engineer",             5,    "senior"),   # fallback to years
    ("DevOps Engineer",             1,    "junior"),   # fallback to years
    ("DevOps Engineer",             None, "mid"),      # default
    ("Platform Engineer",           3,    "mid"),      # 3 yrs = mid
])
def test_detect_seniority(titel, years, expected):
    assert detect_seniority(titel, years) == expected


# ── detect_certifications ─────────────────────────────────────────────────────

def test_detect_certifications_cka():
    assert detect_certifications("CKA certification preferred") == ["CKA"]


def test_detect_certifications_multiple():
    text = "CKAD and AWS Solutions Architect Associate required"
    result = detect_certifications(text)
    assert "CKAD" in result
    assert "AWS-SAA" in result


def test_detect_certifications_terraform():
    assert detect_certifications("HashiCorp Certified Terraform Associate") == ["Terraform"]


def test_detect_certifications_none():
    assert detect_certifications("keine Zertifizierungen notwendig") == []


def test_detect_certifications_azure():
    result = detect_certifications("AZ-104 oder AZ-400 von Vorteil")
    assert "AZ-104" in result
    assert "AZ-400" in result


# ── detect_education ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("Ph.D. in Computer Science",               "phd"),
    ("Promotion oder vergleichbar",              "phd"),
    ("Master-Abschluss in Informatik",          "master"),
    ("M.Sc. in Computer Science",               "master"),
    ("abgeschlossenes Studium",                 "bachelor"),
    ("Hochschulabschluss erforderlich",         "bachelor"),
    ("Fachhochschule oder Uni-Abschluss",       "bachelor"),
    ("IHK-Ausbildung im IT-Bereich",            "ausbildung"),
    ("Berufsausbildung erwünscht",              "ausbildung"),
    ("keine formalen Anforderungen",            "unknown"),
    ("",                                        "unknown"),
])
def test_detect_education(text, expected):
    assert detect_education(text) == expected
