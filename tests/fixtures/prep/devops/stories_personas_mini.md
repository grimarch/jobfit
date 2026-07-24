# Prep roles (devops)

**Draft** generated: 2026-07-22T00:00:00Z

<!-- jobfit:prep-personas:llm-input -->

## S1 — Primary (startup / AI)

**Company:** TestCo
**prep_label:** fit

**JD excerpt:** Build the infrastructure for live AI products.

**JD focus:** Own CI/CD pipelines, containerization, and cloud infrastructure for live AI-driven products. Startup pace; hands-on DevOps; English technical.

**Lead from claims:**
- GitLab CI/CD LMS: 45→10 min deploy
- Terraform + Ansible: 29 resources

**Gaps for this job:**
- **AWS** — Do not claim: Production AWS ownership. Say: Primary clouds GCP + DigitalOcean; patterns transfer.
- **Azure** — Do not claim: Azure production. Say: Target learning, not a CV claim.

**Mock traps:** Do not say "I run AWS" when JD mentions cloud—primary is GCP/DO. Semgrep/ZAP only as "integrated in GitLab CI."

**Language:** EN technical; German available for non-technical intro if needed.

**Stories to write (Phase 2):**
1. GitLab CI/CD LMS redesign: 45→10 min, security gates (Semgrep + ZAP)
2. Terraform + Ansible: GCP multi-stack, DigitalOcean Vault cluster
3. Vault RBAC + AppRole secret delivery
4. JobFit platform ownership: 23-feed ETL, Docker Compose, CLI
5. Kubernetes Helm: umbrella chart migration

---

## S4 — Stretch (hosting / IaC CI/CD)

**Company:** HostingCo
**prep_label:** stretch

**JD excerpt:** Design and operate customer platforms on private cloud and Azure.

**JD focus:** Design and operate multi-customer cloud platforms. Kubernetes, DevOps practices, Terraform/Ansible. German-speaking team, B2B infrastructure.

**Lead from claims:**
- Terraform + Ansible: 29 resources
- Ansible Molecule: 200+ hosts fleet compliance

**Gaps for this job:**
- **AWS** — Do not claim: Production AWS ownership. Say: IaC patterns transfer.
- **Jenkins** — Do not claim: Jenkins admin. Say: GitLab CI owner.

**Mock traps:** Do not claim Azure production; do not say "I run Jenkins"—emphasize GitLab CI depth. IaC portability across platforms.

**Language:** DE B2 (DTB 2024); EN technical terms; on-call flag — historical 2016–2020, not current rotation.

**Stories to write (Phase 2):**
1. Ansible Molecule + fleet compliance: 200+ multi-distro hosts rollout
2. Prometheus + Grafana: 200+ host dashboards, compliance reporting
3. Terraform / IaC multi-stack: 29 resources, state management, multi-cloud
4. Helm umbrella chart migration: PostgreSQL externalization, upgrade validation
5. B2B incident triage (historical): SLA-aligned diagnostics

---

## S2 — Stretch 2 (startup platform + security)

**Company:** PlatCo
**prep_label:** stretch

**JD excerpt:** Own platform foundations end-to-end including AWS and observability.

**JD focus:** Own platform architecture and security foundations for agentic AI. AWS, CI/CD, infrastructure automation, security gates. Early-stage startup; deep ownership; English technical.

**Lead from claims:**
- GitLab CI/CD + security: Semgrep SAST + OWASP ZAP DAST integrated on every run
- Vault RBAC + AppRole: eliminated hardcoded credentials

**Gaps for this job:**
- **AWS** — Do not claim: Production AWS ownership. Say: GCP/DO IaC patterns transfer.
- **IAM** — Do not claim: AWS IAM policies in prod. Say: Vault RBAC + AppRole for app identity.
- **OpenTelemetry** — Do not claim: OTel in production. Say: Prometheus/Grafana/Graphite at 200+ hosts.

**Mock traps:** Do not claim AWS production or IAM policy expertise; not observability specialist—Prom/Grafana is operational tooling; do not claim OTel production.

**Language:** EN technical; German available but not primary for this role.

**Stories to write (Phase 2):**
1. GitLab CI/CD + security gates: Semgrep + ZAP integration, shifting left
2. Vault RBAC + AppRole: secret delivery, onboarding pattern
3. DevSecOps shift-left: Semgrep + ZAP on every commit
4. Prometheus + Grafana observability: 200+ host dashboards for platform teams

---

## Anchors

| Job | One-line anchor |
|---|---|
| S1 | GitLab CI/CD LMS: 45→10 min; owned full infra cycle (GCP/DO/Vault) for live product. |
| S4 | Terraform + Ansible: 29 resources, 200+ multi-distro hosts, GitLab CI, Helm umbrella. |
| S2 | GitLab CI/CD + security gates (Semgrep + ZAP); Vault RBAC + AppRole; ready to ramp on AWS. |

<!-- /jobfit:prep-personas:llm-input -->
