"""Unit tests for jobfit/fetchers/direct/bundesagentur.py — _is_germany_ba."""

import pytest

from jobfit.fetchers.direct.bundesagentur import _is_germany_ba
from tests.conftest import make_ba_job, make_ba_job_no_land


# ── _is_germany_ba ────────────────────────────────────────────────────────────

def test_no_stellenlokationen_field():
    assert _is_germany_ba({}) is True


def test_empty_stellenlokationen():
    assert _is_germany_ba({"stellenlokationen": []}) is True


def test_no_land_in_adresse():
    assert _is_germany_ba(make_ba_job_no_land()) is True


def test_land_deutschland_uppercase():
    assert _is_germany_ba(make_ba_job(["DEUTSCHLAND"])) is True


def test_land_deutschland_lowercase():
    assert _is_germany_ba(make_ba_job(["deutschland"])) is True


def test_land_deutschland_mixed_case():
    assert _is_germany_ba(make_ba_job(["Deutschland"])) is True


def test_land_austria_is_excluded():
    assert _is_germany_ba(make_ba_job(["ÖSTERREICH"])) is False


def test_land_austria_english():
    assert _is_germany_ba(make_ba_job(["AUSTRIA"])) is False


def test_multiple_locs_one_de():
    assert _is_germany_ba(make_ba_job(["DEUTSCHLAND", "ÖSTERREICH"])) is True


def test_multiple_locs_all_foreign():
    assert _is_germany_ba(make_ba_job(["ÖSTERREICH", "POLAND"])) is False
