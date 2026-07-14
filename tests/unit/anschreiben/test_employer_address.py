"""Unit tests for jobfit.anschreiben.employer_address."""

from __future__ import annotations

import json

from jobfit.anschreiben.employer_address import (
    enrich_letter_employer_address,
    resolve_employer_address,
)


def test_resolve_employer_address_from_ba_detail(tmp_path, monkeypatch) -> None:
    details_dir = tmp_path / "bundesagentur_details"
    details_dir.mkdir()
    (details_dir / "10001-1003130898-S.json").write_text(
        json.dumps({
            "stellenlokationen": [{
                "adresse": {
                    "strasse": "Königsbrücker Str.",
                    "hausnummer": "96",
                    "plz": "01099",
                    "ort": "Dresden",
                },
            }],
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "jobfit.anschreiben.employer_address._BA_DETAILS_DIR",
        details_dir,
    )
    monkeypatch.setattr(
        "jobfit.anschreiben.employer_address._BA_SEARCH_FILE",
        tmp_path / "missing.json",
    )

    result = resolve_employer_address("10001-1003130898-S")

    assert result == {
        "street": "Königsbrücker Str. 96",
        "city_line": "01099 Dresden",
    }


def test_resolve_employer_address_falls_back_to_ort(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "jobfit.anschreiben.employer_address._BA_DETAILS_DIR",
        tmp_path / "missing",
    )
    monkeypatch.setattr(
        "jobfit.anschreiben.employer_address._BA_SEARCH_FILE",
        tmp_path / "missing.json",
    )

    result = resolve_employer_address("unknown-refnr", ort_fallback="Berlin")

    assert result == {"street": "", "city_line": "Berlin"}


def test_resolve_employer_address_parses_plz_from_ort() -> None:
    result = resolve_employer_address(
        "everjobs-abc-123",
        ort_fallback="80331 München, Bavaria, Germany",
    )
    assert result == {"street": "", "city_line": "80331 München"}


def test_resolve_employer_address_skips_ba_for_ats_refnr(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "jobfit.anschreiben.employer_address._resolve_bundesagentur",
        lambda refnr: {"street": "Should", "city_line": "Not be used"},
    )
    monkeypatch.setattr(
        "jobfit.anschreiben.employer_address._jobhive_row_location",
        lambda ats, ats_id: "",
    )

    result = resolve_employer_address(
        "ats-personio-999",
        ort_fallback="Berlin",
    )

    assert result == {"street": "", "city_line": "Berlin"}


def test_resolve_employer_address_from_jobhive_parquet(
    tmp_path,
    monkeypatch,
) -> None:
    try:
        import pandas as pd
    except ImportError:
        return

    cache_dir = tmp_path / "jobhive_cache"
    cache_dir.mkdir()
    df = pd.DataFrame({
        "ats_id": [999],
        "location": ["80331 München, Bavaria, Germany"],
    })
    df.to_parquet(cache_dir / "personio.parquet", index=False)

    monkeypatch.setattr(
        "jobfit.anschreiben.employer_address.CACHE_DIR",
        cache_dir,
    )

    result = resolve_employer_address("ats-personio-999")

    assert result == {"street": "", "city_line": "80331 München"}


def test_enrich_letter_employer_address_attaches_fields(
    tmp_path,
    monkeypatch,
) -> None:
    details_dir = tmp_path / "bundesagentur_details"
    details_dir.mkdir()
    (details_dir / "ref-1.json").write_text(
        json.dumps({
            "stellenlokationen": [{
                "adresse": {
                    "strasse": "Musterstraße",
                    "hausnummer": "1",
                    "plz": "80331",
                    "ort": "München",
                },
            }],
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "jobfit.anschreiben.employer_address._BA_DETAILS_DIR",
        details_dir,
    )
    monkeypatch.setattr(
        "jobfit.anschreiben.employer_address._BA_SEARCH_FILE",
        tmp_path / "missing.json",
    )

    letter_data: dict[str, str] = {"firma": "Acme GmbH"}
    enrich_letter_employer_address(
        letter_data,
        {"refnr": "ref-1", "ort": "München"},
    )

    assert letter_data["employer_street"] == "Musterstraße 1"
    assert letter_data["employer_city_line"] == "80331 München"
