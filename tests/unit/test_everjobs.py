"""Unit tests for jobfit/fetchers/direct/everjobs.py."""

from datetime import datetime

import pytest

from jobfit.fetchers.direct.everjobs import (
    _CITY_FROM_TITLE_RE,
    _is_germany,
    _to_job,
)


# ── _CITY_FROM_TITLE_RE ───────────────────────────────────────────────────────

class TestCityFromTitleRe:
    def _extract(self, title: str) -> str:
        m = _CITY_FROM_TITLE_RE.search(title)
        return m.group(1).strip() if m else ""

    def test_single_city(self):
        title = "DevOps Engineer (m/w/d) - Frankfurt @ Acme GmbH [50.000 - 80.000 €]"
        assert self._extract(title) == "Frankfurt"

    def test_umlaut_city(self):
        title = "Platform Engineer (m/w/d) - München @ SomeCo [60.000 - 90.000 €]"
        assert self._extract(title) == "München"

    def test_no_city_direct_at(self):
        # Format without city: "Title (m/w/d) @ Company [salary]"
        title = "Senior DevOps Engineer (m/w/d) @ PACE Mobility GmbH [47.000 - 76.000 €]"
        assert self._extract(title) == ""

    def test_no_city_no_parenthesis(self):
        title = "Cloud Engineer @ Startup GmbH [55.000 €]"
        assert self._extract(title) == ""

    def test_multiple_cities(self):
        title = "SRE (m/w/d) - Berlin, Hamburg @ BigCo [70.000 - 100.000 €]"
        assert self._extract(title) == "Berlin, Hamburg"

    def test_city_with_slash(self):
        title = "Infrastructure Engineer (m/w/d) - Köln/Bonn @ Corp AG [60k]"
        assert self._extract(title) == "Köln/Bonn"

    def test_ignores_salary_dash(self):
        # Salary range contains " - " but regex should not confuse it with city separator
        title = "DevOps Engineer (m/w/d) @ Company GmbH [60.000 - 90.000 €]"
        assert self._extract(title) == ""

    def test_remote_label(self):
        title = "DevOps Engineer (m/w/d) - Remote @ SaaS GmbH [65.000 €]"
        assert self._extract(title) == "Remote"


# ── _is_germany ───────────────────────────────────────────────────────────────

class TestIsGermany:
    def test_germantechjobs_always_true(self):
        assert _is_germany({"site": "germantechjobs"}) is True

    def test_germantechjobs_null_location(self):
        assert _is_germany({"site": "germantechjobs", "location": None}) is True

    def test_berlinstartupjobs_always_true(self):
        assert _is_germany({"site": "berlinstartupjobs"}) is True

    def test_adzuna_country_germany(self):
        assert _is_germany({"site": "adzuna", "location": {"country": "Germany"}}) is True

    def test_adzuna_country_de_lowercase(self):
        assert _is_germany({"site": "adzuna", "location": {"country": "de"}}) is True

    def test_adzuna_country_de_uppercase(self):
        assert _is_germany({"site": "adzuna", "location": {"country": "DE"}}) is True

    def test_adzuna_country_deu(self):
        assert _is_germany({"site": "adzuna", "location": {"country": "deu"}}) is True

    def test_adzuna_country_deutschland(self):
        assert _is_germany({"site": "adzuna", "location": {"country": "Deutschland"}}) is True

    def test_adzuna_city_berlin(self):
        assert _is_germany({"site": "adzuna", "location": {"country": "", "city": "Berlin"}}) is True

    def test_adzuna_us_is_excluded(self):
        assert _is_germany({"site": "adzuna", "location": {"country": "US", "city": "New York"}}) is False

    def test_adzuna_null_location(self):
        assert _is_germany({"site": "adzuna", "location": None}) is False

    def test_adzuna_empty_location(self):
        assert _is_germany({"site": "adzuna", "location": {}}) is False


# ── _to_job ───────────────────────────────────────────────────────────────────

_NOW = datetime(2026, 7, 7, 12, 0, 0)


def _raw(
    *,
    site: str = "germantechjobs",
    job_id: str = "acme-DevOps-Engineer",
    title: str = "DevOps Engineer (m/w/d) @ Acme GmbH [55.000 - 75.000 €]",
    company: str = "Acme GmbH",
    url: str = "https://example.com/job/1",
    location: dict | None = None,
    compensation: dict | None = None,
    job_type: list[str] | None = None,
    description: str = "Job description here.",
) -> dict:
    return {
        "site": site,
        "id": job_id,
        "title": title,
        "companyName": company,
        "jobUrl": url,
        "location": location or {},
        "compensation": compensation or {},
        "jobType": job_type or ["fulltime"],
        "description": description,
    }


class TestToJob:
    def test_refnr_no_double_prefix(self):
        job = _to_job(_raw(site="germantechjobs", job_id="germantechjobs-Acme-DevOps"), "devops", _NOW)
        assert job.refnr == "everjobs-germantechjobs-Acme-DevOps"
        assert "everjobs-germantechjobs-germantechjobs" not in job.refnr

    def test_refnr_adzuna(self):
        job = _to_job(_raw(site="adzuna", job_id="abc123"), "devops", _NOW)
        assert job.refnr == "everjobs-abc123"

    def test_via_is_everjobs(self):
        job = _to_job(_raw(), "devops", _NOW)
        assert job.via == "everjobs"

    def test_partner_name(self):
        job = _to_job(_raw(site="germantechjobs"), "devops", _NOW)
        assert job.partner_name == "everjobs/germantechjobs"

    def test_ort_from_location_city(self):
        raw = _raw(location={"city": "Berlin", "state": None, "country": "Germany"})
        job = _to_job(raw, "devops", _NOW)
        assert job.ort_raw == "Berlin"

    def test_ort_city_and_state(self):
        raw = _raw(location={"city": "Munich", "state": "Bavaria", "country": "Germany"})
        job = _to_job(raw, "devops", _NOW)
        assert job.ort_raw == "Munich, Bavaria"

    def test_ort_fallback_from_title(self):
        raw = _raw(
            location={},
            title="DevOps Engineer (m/w/d) - Frankfurt @ Acme GmbH [55.000 €]",
        )
        job = _to_job(raw, "devops", _NOW)
        assert job.ort_raw == "Frankfurt"

    def test_ort_empty_when_no_city_in_title(self):
        raw = _raw(
            location={},
            title="Senior DevOps Engineer (m/w/d) @ PACE Mobility GmbH [47.000 - 76.000 €]",
        )
        job = _to_job(raw, "devops", _NOW)
        assert job.ort_raw == ""

    def test_salary_yearly(self):
        raw = _raw(compensation={"interval": "yearly", "minAmount": 60000, "maxAmount": 90000, "currency": "EUR"})
        job = _to_job(raw, "devops", _NOW)
        assert job.salary_min_raw == 60000
        assert job.salary_max_raw == 90000
        assert job.salary_period == "YEAR"
        assert job.salary_currency == "EUR"

    def test_salary_monthly(self):
        raw = _raw(compensation={"interval": "monthly", "minAmount": 5000, "maxAmount": 7000, "currency": "EUR"})
        job = _to_job(raw, "devops", _NOW)
        assert job.salary_period == "MONTH"

    def test_salary_hourly(self):
        raw = _raw(compensation={"interval": "hourly", "minAmount": 40, "maxAmount": 60, "currency": "EUR"})
        job = _to_job(raw, "devops", _NOW)
        assert job.salary_period == "HOUR"

    def test_salary_unknown_interval(self):
        raw = _raw(compensation={"interval": "weekly", "minAmount": 1000})
        job = _to_job(raw, "devops", _NOW)
        assert job.salary_period == "MONTH"

    def test_vollzeit_fulltime(self):
        job = _to_job(_raw(job_type=["fulltime"]), "devops", _NOW)
        assert job.vollzeit is True

    def test_vollzeit_parttime(self):
        job = _to_job(_raw(job_type=["parttime"]), "devops", _NOW)
        assert job.vollzeit is False

    def test_vollzeit_default_when_empty(self):
        job = _to_job(_raw(job_type=[]), "devops", _NOW)
        assert job.vollzeit is True

    def test_fields_basic(self):
        raw = _raw(title="DevOps Engineer (m/w/d) @ Acme GmbH", company="Acme GmbH", url="https://example.com/1")
        job = _to_job(raw, "devops", _NOW)
        assert job.titel == "DevOps Engineer (m/w/d) @ Acme GmbH"
        assert job.firma == "Acme GmbH"
        assert job.externe_url == "https://example.com/1"
        assert job.role == "devops"
        assert job.ats_source == "germantechjobs"
