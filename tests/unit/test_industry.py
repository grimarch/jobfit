"""Unit tests for jobfit/industry.py — normalize()."""

import pytest

from jobfit.industry import normalize


@pytest.mark.parametrize("raw,expected", [
    ("fintech startup",             "FinTech"),
    ("InsurTech platform",          "Insurance"),
    ("insurance company",           "Insurance"),
    ("Banking services",            "Banking"),
    ("healthtech / medtech",        "HealthTech / MedTech"),
    ("healthcare platform",         "HealthTech / MedTech"),
    ("Defense & Aerospace",         "Defense & Aerospace"),
    ("Energy / CleanTech",          "Energy / CleanTech"),
    ("Automotive OEM",              "Automotive"),
    ("Telecom provider",            "Telecom"),
    ("Gaming / Media company",      "Gaming / Media"),
    ("streaming platform",          "Gaming / Media"),
    ("Logistics and supply chain",  "Logistics"),
    ("eCommerce platform",          "eCommerce / Retail"),
    ("AI/ML services",              "AI / ML"),
    ("machine learning startup",    "AI / ML"),
    ("Cybersecurity firm",          "Cybersecurity"),
    ("IT security company",         "Cybersecurity"),
    ("EdTech platform",             "EdTech"),
    ("Manufacturing company",       "Manufacturing"),
    ("Public Sector",               "Public Sector"),
    ("IT Services B2B",             "IT Services / B2B"),
    ("SaaS cloud platform",         "SaaS / Cloud"),
    ("software company",            "SaaS / Cloud"),
    ("unknown XYZ Corp",            "Other"),
    ("",                            "Other"),
    (None,                          "Other"),
])
def test_normalize(raw, expected):
    assert normalize(raw) == expected


def test_normalize_case_insensitive():
    assert normalize("FINTECH") == normalize("fintech")
