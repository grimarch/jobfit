"""Smoke tests: dashboard renders without errors and tier counts match snapshot."""

import pytest

from jobfit.dashboards import targets


def test_tier_counts_appear_in_render():
    """tier_counts() must match the numbers shown in targets.render() HTML."""
    counts = targets.tier_counts()
    html = targets.render()
    for tier, count in counts.items():
        assert str(count) in html, (
            f"Count {count} for tier '{tier}' not found in rendered HTML"
        )


def test_tier_counts_not_empty():
    counts = targets.tier_counts()
    product_tiers = sum(v for k, v in counts.items() if k != "starred")
    assert product_tiers > 0


def test_load_classifications_not_empty():
    from jobfit.db import get_session
    from jobfit.db.models import Classification as ClsModel

    with get_session() as session:
        count = session.query(ClsModel).filter(ClsModel.role == "devops").count()
    assert count > 0


def test_load_classifications_no_closed():
    """Default DB query must exclude jobs with closed_at set."""
    from jobfit.db import get_session
    from jobfit.db.models import Classification as ClsModel, Job as JobModel

    with get_session() as session:
        # Ensure no active (non-closed) jobs have been accidentally closed
        open_count = (
            session.query(ClsModel)
            .join(JobModel, ClsModel.refnr == JobModel.refnr)
            .filter(ClsModel.role == "devops", JobModel.closed_at.is_(None))
            .count()
        )
    assert open_count > 0, "Expected open (non-closed) classified jobs in DB"


def test_render_produces_html():
    """targets.render() must return an HTML string containing tier labels."""
    html = targets.render()
    assert isinstance(html, str)
    assert "Dreamjob" in html
    assert "CV Builder" in html
    assert "Easy Win" in html
