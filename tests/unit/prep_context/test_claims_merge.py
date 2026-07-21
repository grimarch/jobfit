"""Unit tests for prep claims merge helpers."""

from jobfit.prep_context.claims_merge import parse_gaps_table

_LEGACY_GAPS = """\
## Gaps vs starred / market (honest transfer lines)

| Gap | Do not claim | Say instead |
|---|---|---|
| **AWS** | No AWS prod | Transfer narrative |
| **Azure** | — | Learning scope |
"""

_NEW_GAPS = """\
## Gaps vs prep shortlist (honest transfer lines)

| Gap | Jobs | Count | Do not claim | Say instead |
|---|---|---:|---|---|
| **AWS** | S1, S2 | 2 | No AWS prod | Transfer narrative |
"""


def test_parse_gaps_table_legacy_two_column():
    parsed = parse_gaps_table(_LEGACY_GAPS)
    assert parsed["AWS"]["do_not_claim"] == "No AWS prod"
    assert parsed["AWS"]["say_instead"] == "Transfer narrative"


def test_parse_gaps_table_five_column():
    parsed = parse_gaps_table(_NEW_GAPS)
    assert parsed["AWS"]["jobs"] == "S1, S2"
    assert parsed["AWS"]["count"] == "2"
    assert parsed["AWS"]["say_instead"] == "Transfer narrative"
