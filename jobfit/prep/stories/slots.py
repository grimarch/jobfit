"""Story catalog for prep stories pipeline — devops role v1."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StorySlot:
    id: str
    title: str
    claims_labels: tuple[str, ...]
    work_comp: str  # "WORK_COMP_1" | "WORK_COMP_2"
    optional: bool = False


CATALOG: dict[str, StorySlot] = {
    "s1-ci-cd": StorySlot(
        id="s1-ci-cd",
        title="CI/CD LMS 45→10 min",
        claims_labels=(
            "GitLab CI/CD — design, stages, deploy automation",
            "DevSecOps / SAST / DAST",
        ),
        work_comp="WORK_COMP_1",
    ),
    "s1-terraform": StorySlot(
        id="s1-terraform",
        title="Terraform / IaC multi-stack (29 resources)",
        claims_labels=(
            "Terraform / IaC — multi-stack, remote state",
            "GCP — production infrastructure",
            "DigitalOcean — infrastructure",
        ),
        work_comp="WORK_COMP_1",
    ),
    "s1-vault": StorySlot(
        id="s1-vault",
        title="Vault RBAC + AppRole secret delivery",
        claims_labels=(
            "HashiCorp Vault — secrets, RBAC, delivery pattern",
        ),
        work_comp="WORK_COMP_1",
    ),
    "s1-jobfit": StorySlot(
        id="s1-jobfit",
        title="JobFit platform ownership (23 feeds, 30–40 min)",
        claims_labels=(
            "Docker — containerized workloads",
            "End-to-end platform ownership",
        ),
        work_comp="WORK_COMP_1",
    ),
    "s1-helm-opt": StorySlot(
        id="s1-helm-opt",
        title="Helm umbrella chart migration",
        claims_labels=(
            "Kubernetes / Helm — chart maintenance, upgrades",
        ),
        work_comp="WORK_COMP_2",
        optional=True,
    ),
    "s4-ansible": StorySlot(
        id="s4-ansible",
        title="Ansible Molecule + fleet compliance (200+ hosts)",
        claims_labels=(
            "Ansible — provisioning + fleet rollout",
            "Fleet monitoring & compliance observability",
        ),
        work_comp="WORK_COMP_2",
    ),
    "s4-observability": StorySlot(
        id="s4-observability",
        title="Prometheus + Grafana observability (200+ hosts)",
        claims_labels=(
            "Prometheus + Grafana (+ Graphite) at scale",
            "Fleet monitoring & compliance observability",
        ),
        work_comp="WORK_COMP_2",
    ),
    "s2-devsecops": StorySlot(
        id="s2-devsecops",
        title="DevSecOps shift-left (Semgrep + ZAP)",
        claims_labels=(
            "DevSecOps / SAST / DAST",
            "Semgrep (SAST) in CI pipelines",
            "OWASP ZAP (DAST) in CI pipelines",
        ),
        work_comp="WORK_COMP_1",
    ),
    "s4-triage-opt": StorySlot(
        id="s4-triage-opt",
        title="B2B incident triage (historical, 2016–2020)",
        claims_labels=(
            "Network troubleshooting",
            "On-call / incident support (historical)",
        ),
        work_comp="WORK_COMP_2",
        optional=True,
    ),
}

# Per-mock rehearsal order — local index 1…N.
# Mirrors format B reference (stories.md).
MOCK_STORY_ORDER: dict[str, list[str]] = {
    "S1": ["s1-ci-cd", "s1-terraform", "s1-vault", "s1-jobfit", "s1-helm-opt"],
    "S4": ["s4-ansible", "s4-observability", "s1-terraform", "s1-helm-opt", "s4-triage-opt"],
    "S2": ["s1-ci-cd", "s1-vault", "s2-devsecops", "s4-observability"],
}


def stories_for_mock(mock_id: str) -> list[StorySlot]:
    """Return ordered story slots for a given mock id."""
    order = MOCK_STORY_ORDER.get(mock_id, [])
    return [CATALOG[sid] for sid in order if sid in CATALOG]
