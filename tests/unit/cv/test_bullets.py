"""Unit tests for jobfit.cv.bullets."""

import textwrap

from jobfit.cv.bullets import (
    extract_trailing_project_label,
    parse_experience_bullets_by_period,
    restore_experience_project_labels,
    strip_trailing_project_label,
)


def test_extract_trailing_project_label_recognizes_trailing_suffix() -> None:
    bullet = (
        "Built secure CI/CD pipelines with GitHub Actions and GitLab CI, "
        "including automated testing, vulnerability scanning (Bandit, Trivy, Safety), "
        "and staged deployments (Alpha Platform)"
    )
    assert extract_trailing_project_label(bullet) == "Alpha Platform"


def test_extract_trailing_suffix_accepts_any_trailing_parenthetical() -> None:
    bullet = (
        "Developed GitLab CI/CD pipelines with artifact publishing to object storage (S3)"
    )
    assert extract_trailing_project_label(bullet) == "S3"


def test_strip_trailing_project_label() -> None:
    bullet = "Implemented secrets management with RBAC and audit logging (Beta Infra)"
    assert strip_trailing_project_label(bullet) == (
        "Implemented secrets management with RBAC and audit logging"
    )


def test_parse_experience_bullets_by_period() -> None:
    cv_text = textwrap.dedent("""\
        PROFESSIONAL EXPERIENCE
        Platform Engineer – Acme Corp                                              Jan 2023 - Present
        Berlin, Germany
           Built secure CI/CD pipelines with GitHub Actions (Alpha Platform)
           Built an internal analytics dashboard (Project Gamma)

        DevOps Engineer – Example GmbH                                           May 2020 - Aug 2021
        Hamburg, Germany
           Developed GitLab CI/CD pipelines with object storage (S3)
    """)
    by_period = parse_experience_bullets_by_period(cv_text)

    recent = by_period["2023-present"]
    assert len(recent) == 2
    assert recent[0][1] == "Alpha Platform"
    assert recent[1][1] == "Project Gamma"

    earlier = by_period["2020-2021"]
    assert len(earlier) == 1
    assert earlier[0][1] == "S3"


def test_restore_experience_project_labels() -> None:
    cv_text = textwrap.dedent("""\
        PROFESSIONAL EXPERIENCE
        Platform Engineer – Acme Corp                                              Jan 2023 - Present
        Berlin, Germany
           Built secure CI/CD pipelines with GitHub Actions and GitLab CI (Alpha Platform)
           Built an internal analytics dashboard (Project Gamma)
    """)
    cv_data = {
        "experience": [
            {
                "title": "Platform Engineer",
                "period": "01.2023 – Present",
                "bullets": [
                    "Built secure CI/CD pipelines with GitHub Actions and GitLab CI",
                    "Built an internal analytics dashboard",
                ],
            }
        ],
    }

    restore_experience_project_labels(cv_data, cv_text)

    assert cv_data["experience"][0]["bullets"] == [
        "Built secure CI/CD pipelines with GitHub Actions and GitLab CI (Alpha Platform)",
        "Built an internal analytics dashboard (Project Gamma)",
    ]


def test_restore_experience_project_labels_keeps_existing_suffix() -> None:
    cv_text = textwrap.dedent("""\
        PROFESSIONAL EXPERIENCE
        Platform Engineer – Acme Corp                                              Jan 2023 - Present
           Built secure CI/CD pipelines with GitHub Actions (Alpha Platform)
    """)
    cv_data = {
        "experience": [
            {
                "period": "01.2023 – Present",
                "bullets": [
                    "Built secure CI/CD pipelines with GitHub Actions (Alpha Platform)"
                ],
            }
        ],
    }

    restore_experience_project_labels(cv_data, cv_text)

    assert cv_data["experience"][0]["bullets"] == [
        "Built secure CI/CD pipelines with GitHub Actions (Alpha Platform)"
    ]
