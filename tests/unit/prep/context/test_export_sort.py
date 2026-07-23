"""Unit tests for starred sort order in prep context export."""

from __future__ import annotations

from jobfit.prep.context.export import _sort_starred_records


def test_sort_starred_records_matches_dashboard_score_order():
    """Higher score first — same primary key as targets Starred tab."""
    records = [
        {
            "id": "",
            "refnr": "low",
            "score": 10,
            "company_stage": "startup",
            "work_mode": "onsite",
            "_sort_firma": "Zebra",
        },
        {
            "id": "",
            "refnr": "high",
            "score": 12,
            "company_stage": "startup",
            "work_mode": "onsite",
            "_sort_firma": "Alpha",
        },
    ]
    ordered = _sort_starred_records(records)
    assert [r["refnr"] for r in ordered] == ["high", "low"]
    assert [r["id"] for r in ordered] == ["S1", "S2"]
    assert all("_sort_firma" not in r for r in ordered)


def test_sort_starred_records_tiebreak_work_mode():
    """Equal score: remote before hybrid before onsite (dashboard MODE_ORDER)."""
    records = [
        {
            "id": "",
            "refnr": "onsite",
            "score": 12,
            "company_stage": "startup",
            "work_mode": "onsite",
            "_sort_firma": "A",
        },
        {
            "id": "",
            "refnr": "hybrid",
            "score": 12,
            "company_stage": "startup",
            "work_mode": "hybrid",
            "_sort_firma": "A",
        },
    ]
    ordered = _sort_starred_records(records)
    assert [r["refnr"] for r in ordered] == ["hybrid", "onsite"]
    assert ordered[0]["id"] == "S1"
