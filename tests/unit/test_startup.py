"""Unit tests for startup DB prerequisite checks."""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://jobfit:jobfit@localhost:5432/jobfit_test")

from unittest.mock import MagicMock, patch

import pytest

from jobfit.roles import ROLES
from jobfit.startup import check_startup, require_product_jobs


def _role():
    return ROLES["devops"]


@patch("jobfit.db.get_session")
@patch("jobfit.classify.unclassified_count")
def test_require_product_jobs_no_jobs(mock_unclassified, mock_get_session):
    session = MagicMock()
    session.query.return_value.filter.return_value.count.return_value = 0
    mock_get_session.return_value.__enter__.return_value = session

    with pytest.raises(RuntimeError, match="No jobs in DB"):
        require_product_jobs(_role(), [], [])

    mock_unclassified.assert_not_called()


@patch("jobfit.db.get_session")
@patch("jobfit.classify.unclassified_count", return_value=3)
def test_require_product_jobs_unclassified(mock_unclassified, mock_get_session):
    session = MagicMock()
    session.query.return_value.filter.return_value.count.return_value = 5
    mock_get_session.return_value.__enter__.return_value = session

    with pytest.raises(RuntimeError, match="3 job\\(s\\) not classified"):
        require_product_jobs(_role(), [], [])

    mock_unclassified.assert_called_once_with("devops")


@patch("jobfit.db.get_session")
@patch("jobfit.classify.unclassified_count", return_value=0)
def test_require_product_jobs_no_product_companies(mock_unclassified, mock_get_session):
    session = MagicMock()
    session.query.return_value.filter.return_value.count.return_value = 5
    mock_get_session.return_value.__enter__.return_value = session

    with pytest.raises(RuntimeError, match="No product company jobs"):
        require_product_jobs(_role(), [], [])


@patch("jobfit.db.get_session")
@patch("jobfit.classify.unclassified_count", return_value=0)
def test_require_product_jobs_missing_descriptions(mock_unclassified, mock_get_session):
    session = MagicMock()
    session.query.return_value.filter.return_value.count.return_value = 5
    mock_get_session.return_value.__enter__.return_value = session

    with pytest.raises(RuntimeError, match="descriptions are missing"):
        require_product_jobs(_role(), ["ref-1"], [])


def test_require_product_jobs_ok_with_data():
    require_product_jobs(_role(), ["ref-1"], ["ref-1"])


@patch("jobfit.startup.load_product_job_refs", return_value=([], []))
@patch("jobfit.db.get_session")
@patch("jobfit.classify.unclassified_count", return_value=0)
def test_check_startup_propagates_error(mock_unclassified, mock_get_session, _mock_load):
    session = MagicMock()
    session.query.return_value.filter.return_value.count.return_value = 0
    mock_get_session.return_value.__enter__.return_value = session

    with pytest.raises(RuntimeError, match="No jobs in DB"):
        check_startup("devops")
