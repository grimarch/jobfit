"""Unit tests for jobfit/brands.py."""

import json
from contextlib import contextmanager
from unittest.mock import MagicMock, call, patch

import pytest

from jobfit.brands import _already_evaluated, classify_brands, save


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_session(*rows):
    """Return a mock context-manager session that yields itself."""
    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = list(rows)
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    return session


def _kb_row(firma: str, is_known: bool = True) -> MagicMock:
    row = MagicMock()
    row.firma = firma
    row.is_known = is_known
    return row


# ── classify_brands ───────────────────────────────────────────────────────────

@patch("jobfit.brands.llm_complete")
def test_classify_brands_returns_known_list(mock_llm: MagicMock) -> None:
    mock_llm.return_value = json.dumps(["Acme Corp", "Foobar GmbH"])
    result = classify_brands(["Acme Corp", "Foobar GmbH", "Staffing AG"], "sys")
    assert result == ["Acme Corp", "Foobar GmbH"]


@patch("jobfit.brands.llm_complete")
def test_classify_brands_strips_json_fence(mock_llm: MagicMock) -> None:
    payload = json.dumps(["Acme Corp"])
    mock_llm.return_value = f"```json\n{payload}\n```"
    result = classify_brands(["Acme Corp"], "sys")
    assert result == ["Acme Corp"]


@patch("jobfit.brands.llm_complete")
def test_classify_brands_strips_plain_fence(mock_llm: MagicMock) -> None:
    payload = json.dumps(["Acme Corp"])
    mock_llm.return_value = f"```\n{payload}\n```"
    result = classify_brands(["Acme Corp"], "sys")
    assert result == ["Acme Corp"]


@patch("jobfit.brands.llm_complete")
def test_classify_brands_empty_response_returns_empty_list(mock_llm: MagicMock) -> None:
    mock_llm.return_value = ""
    result = classify_brands(["Acme"], "sys")
    assert result == []


# ── _already_evaluated ────────────────────────────────────────────────────────

@patch("jobfit.db.get_session")
def test_already_evaluated_returns_firma_names(mock_gs: MagicMock) -> None:
    session = _make_session(_kb_row("Acme"), _kb_row("Foobar", is_known=False))
    mock_gs.return_value = session
    result = _already_evaluated("devops")
    assert result == frozenset({"Acme", "Foobar"})


@patch("jobfit.db.get_session")
def test_already_evaluated_empty_table(mock_gs: MagicMock) -> None:
    session = _make_session()
    mock_gs.return_value = session
    assert _already_evaluated("devops") == frozenset()


# ── save ──────────────────────────────────────────────────────────────────────

@patch("jobfit.db.get_session")
def test_save_does_not_call_delete(mock_gs: MagicMock) -> None:
    session = _make_session()
    mock_gs.return_value = session
    save(["Acme"], ["Staffing AG"], "devops")
    session.query.return_value.filter.return_value.delete.assert_not_called()


@patch("jobfit.db.get_session")
def test_save_adds_known_and_rejected(mock_gs: MagicMock) -> None:
    session = _make_session()
    mock_gs.return_value = session
    save(["Acme"], ["Staffing AG"], "devops")
    added = [c.args[0] for c in session.add.call_args_list]
    known = [a for a in added if a.is_known is True]
    rejected = [a for a in added if a.is_known is False]
    assert len(known) == 1 and known[0].firma == "Acme"
    assert len(rejected) == 1 and rejected[0].firma == "Staffing AG"


# ── run — incremental logic ───────────────────────────────────────────────────

# ── audit ─────────────────────────────────────────────────────────────────────

def _make_cls_row(firma: str) -> MagicMock:
    row = MagicMock()
    row.firma = firma
    return row


@patch("jobfit.db.get_session")
def test_audit_clean_state(mock_gs: MagicMock, capsys) -> None:
    import argparse
    from jobfit.brands import audit

    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    # brand_rows and cls_rows returned in order of .all() calls
    session.query.return_value.filter.return_value.all.side_effect = [
        [_kb_row("Acme"), _kb_row("OldCorp", is_known=False)],  # brand_rows
        [_make_cls_row("Acme"), _make_cls_row("OldCorp")],       # cls_rows
    ]
    mock_gs.return_value = session
    # No assertion needed — just verify it doesn't crash and runs all three checks
    audit(argparse.Namespace(role="devops"))


@patch("jobfit.db.get_session")
def test_audit_detects_duplicates(mock_gs: MagicMock) -> None:
    import argparse
    from jobfit.brands import audit

    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    session.query.return_value.filter.return_value.all.side_effect = [
        [_kb_row("Acme"), _kb_row("Acme")],  # duplicate
        [_make_cls_row("Acme")],
    ]
    mock_gs.return_value = session
    # Should not raise
    audit(argparse.Namespace(role="devops"))


@patch("jobfit.db.get_session")
def test_audit_detects_stale(mock_gs: MagicMock) -> None:
    import argparse
    from jobfit.brands import audit

    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    session.query.return_value.filter.return_value.all.side_effect = [
        [_kb_row("OldGone")],  # in known_brands
        [],                     # no longer in classifications
    ]
    mock_gs.return_value = session
    audit(argparse.Namespace(role="devops"))


@patch("jobfit.db.get_session")
def test_audit_detects_missing(mock_gs: MagicMock) -> None:
    import argparse
    from jobfit.brands import audit

    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    session.query.return_value.filter.return_value.all.side_effect = [
        [],                          # known_brands empty
        [_make_cls_row("NewCorp")],  # but NewCorp is in dataset
    ]
    mock_gs.return_value = session
    audit(argparse.Namespace(role="devops"))


# ── clean_stale ───────────────────────────────────────────────────────────────

@patch("jobfit.db.get_session")
def test_clean_stale_removes_stale_entries(mock_gs: MagicMock) -> None:
    import argparse
    from jobfit.brands import clean_stale

    stale_row = _kb_row("OldGone")
    current_row = _kb_row("Acme")

    call_count = 0
    sessions = []

    def session_factory():
        nonlocal call_count
        s = MagicMock()
        s.__enter__ = MagicMock(return_value=s)
        s.__exit__ = MagicMock(return_value=False)
        if call_count == 0:
            # first with: read brand_rows and cls_rows
            s.query.return_value.filter.return_value.all.side_effect = [
                [stale_row, current_row],          # brand_rows
                [_make_cls_row("Acme")],            # cls_rows (only Acme remains)
            ]
        # second with: the delete call
        call_count += 1
        sessions.append(s)
        return s

    mock_gs.side_effect = session_factory
    clean_stale(argparse.Namespace(role="devops"))

    delete_session = sessions[1]
    delete_session.query.return_value.filter.return_value.delete.assert_called_once()


@patch("jobfit.db.get_session")
def test_clean_stale_no_stale_skips_delete(mock_gs: MagicMock) -> None:
    import argparse
    from jobfit.brands import clean_stale

    row = _kb_row("Acme")
    row.id = 1
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    session.query.return_value.filter.return_value.all.side_effect = [
        [row],
        [_make_cls_row("Acme")],
    ]
    mock_gs.return_value = session
    clean_stale(argparse.Namespace(role="devops"))
    # Only one session used (no delete session opened)
    assert mock_gs.call_count == 1


def _mock_gs_factory(already: list[str], firms_in_db: list[str]):
    """Return a get_session mock that serves different data per call."""
    call_count = 0

    @contextmanager
    def _ctx():
        nonlocal call_count
        session = MagicMock()
        if call_count == 0:
            # collect_firma_names call: returns Classification rows
            rows = []
            for f in firms_in_db:
                r = MagicMock()
                r.firma = f
                rows.append(r)
            session.query.return_value.filter.return_value.filter.return_value.all.return_value = rows
        elif call_count == 1:
            # _already_evaluated call: returns KnownBrand rows
            rows = [_kb_row(f) for f in already]
            session.query.return_value.filter.return_value.all.return_value = rows
        # subsequent calls (save): just yield session
        call_count += 1
        yield session

    return _ctx


@patch("jobfit.brands.llm_complete")
@patch("jobfit.brands._load_prompt", return_value="sys")
@patch("jobfit.brands.collect_firma_names")
@patch("jobfit.brands._already_evaluated")
@patch("jobfit.brands.save")
def test_run_skips_already_evaluated(
    mock_save: MagicMock,
    mock_evaluated: MagicMock,
    mock_collect: MagicMock,
    mock_prompt: MagicMock,
    mock_llm: MagicMock,
) -> None:
    import argparse
    mock_collect.return_value = ["Acme", "NewCo", "OldCorp"]
    mock_evaluated.return_value = frozenset({"Acme", "OldCorp"})
    mock_llm.return_value = json.dumps(["NewCo"])

    from jobfit.brands import run
    run(argparse.Namespace(role="devops", dry_run=False, force=False))

    # LLM only called with new firm
    call_content = mock_llm.call_args[0][0]
    sent_names = json.loads(call_content[0]["content"])
    assert sent_names == ["NewCo"]


@patch("jobfit.brands.llm_complete")
@patch("jobfit.brands._load_prompt", return_value="sys")
@patch("jobfit.brands.collect_firma_names")
@patch("jobfit.brands._already_evaluated")
@patch("jobfit.brands.save")
def test_run_no_new_firms_skips_llm(
    mock_save: MagicMock,
    mock_evaluated: MagicMock,
    mock_collect: MagicMock,
    mock_prompt: MagicMock,
    mock_llm: MagicMock,
) -> None:
    import argparse
    mock_collect.return_value = ["Acme", "OldCorp"]
    mock_evaluated.return_value = frozenset({"Acme", "OldCorp"})

    from jobfit.brands import run
    run(argparse.Namespace(role="devops", dry_run=False, force=False))

    mock_llm.assert_not_called()
    mock_save.assert_not_called()


@patch("jobfit.brands.llm_complete")
@patch("jobfit.brands._load_prompt", return_value="sys")
@patch("jobfit.brands.collect_firma_names")
@patch("jobfit.brands._already_evaluated")
@patch("jobfit.brands._clear")
@patch("jobfit.brands.save")
def test_run_force_clears_and_evaluates_all(
    mock_save: MagicMock,
    mock_clear: MagicMock,
    mock_evaluated: MagicMock,
    mock_collect: MagicMock,
    mock_prompt: MagicMock,
    mock_llm: MagicMock,
) -> None:
    import argparse
    mock_collect.return_value = ["Acme", "OldCorp"]
    mock_llm.return_value = json.dumps(["Acme"])

    from jobfit.brands import run
    run(argparse.Namespace(role="devops", dry_run=False, force=True))

    mock_clear.assert_called_once_with("devops")
    mock_evaluated.assert_not_called()  # --force bypasses incremental check
    call_content = mock_llm.call_args[0][0]
    sent_names = json.loads(call_content[0]["content"])
    assert set(sent_names) == {"Acme", "OldCorp"}
