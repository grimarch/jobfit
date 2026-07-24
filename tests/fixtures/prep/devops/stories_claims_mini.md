**Reviewed:** 2026-07-22

# Claim → Evidence (devops)

**Draft** generated: 2026-07-22T00:00:00Z

## Core DevOps & platform

| Claim (interview) | Evidence (CV bullet + metric) | Status |
|---|---|---|
| **GitLab CI/CD — design, stages, deploy automation** | Designed GitLab CI/CD pipelines for the LMS with Semgrep SAST and OWASP ZAP DAST configs, and staged child-pipeline deployments — reducing deploy effort from approximately 45 minutes to 10 minutes. ([WORK_COMP_1]) | ok |
| **GitLab CI/CD — build/test/release for packages** | Developed GitLab CI/CD pipelines for multi-distro builds, security scanning, and artifact publishing. ([WORK_COMP_2]) | ok |
| **Terraform / IaC — multi-stack, remote state** | Provisioned infrastructure with Terraform and Ansible on GCP and DigitalOcean (Vault Cloud Infra: 5-node Raft cluster), managing 29 Terraform-managed resources across 2 project stacks. ([WORK_COMP_1]) | ok |
| **Ansible — provisioning + fleet rollout** | Authored an Ansible role with Molecule testing for fleet compliance monitoring across 200+ production hosts. ([WORK_COMP_2]) | ok |
| **Kubernetes / Helm — chart maintenance, upgrades** | Replaced a hard-to-maintain Helm fork with an umbrella chart, externalizing PostgreSQL for controlled database upgrades. ([WORK_COMP_2]) | ok |
| **Docker — containerized workloads** | Built JobFit: multi-source ETL from 23 feeds, PostgreSQL, Docker Compose, FastAPI — reducing market research from weeks to 30–40 minutes per cycle. ([WORK_COMP_1]) | ok |
| **HashiCorp Vault — secrets, RBAC, delivery pattern** | Implemented HashiCorp Vault with RBAC, AppRole + Vault Agent for GrimWaves API, eliminating hardcoded credentials. ([WORK_COMP_1]) | ok |
| **DevSecOps / SAST / DAST** | Integrated Semgrep and OWASP ZAP into GitLab CI for the LMS, enabling security scans on every pipeline run and shifting vulnerability feedback to same-day automated reports. ([WORK_COMP_1]) | ok |
| **End-to-end platform ownership** | Built JobFit: multi-source ETL from 23 feeds, PostgreSQL, Docker Compose, FastAPI — reducing market research from weeks to 30–40 minutes per cycle. ([WORK_COMP_1]) | ok |

---

## Observability

| Claim (interview) | Evidence (CV bullet + metric) | Status |
|---|---|---|
| **Prometheus + Grafana (+ Graphite) at scale** | Built Grafana dashboards for host health using Prometheus and Graphite, giving ops teams visibility into 200+ monitored hosts. ([WORK_COMP_2]) | ok |
| **Fleet monitoring & compliance observability** | Built fleet compliance monitoring across Gentoo, Debian, and Ubuntu (200+ hosts), improving compliance visibility from weekly manual checks to daily automated reporting. ([WORK_COMP_2]) | ok |

---

## Security tools

| Claim (interview) | Evidence (CV bullet + metric) | Status |
|---|---|---|
| **Semgrep (SAST) in CI pipelines** | Integrated Semgrep rule sets into GitLab CI for the LMS Platform, enabling security scans on every run. ([WORK_COMP_1]) | ok |
| **OWASP ZAP (DAST) in CI pipelines** | Integrated OWASP ZAP into GitLab CI for the LMS Platform, enabling DAST on every pipeline run. ([WORK_COMP_1]) | ok |

---

## Cloud & storage

| Claim (interview) | Evidence (CV bullet + metric) | Status |
|---|---|---|
| **GCP — production infrastructure** | Provisioned GCP infrastructure with Terraform (LMS VPC, compute, DNS, firewalls); GCS remote state. ([WORK_COMP_1]) | ok |
| **DigitalOcean — infrastructure** | Provisioned DigitalOcean Vault Cloud Infra: 5-node Raft cluster. ([WORK_COMP_1]) | ok |

---

## Linux

| Claim (interview) | Evidence (CV bullet + metric) | Status |
|---|---|---|
| **Network troubleshooting** | Provided 1st- and 2nd-level B2B support, diagnosing incidents with tcpdump/Wireshark, traceroute/mtr, nmap. ([WORK_COMP_2]) | ok |
| **On-call / incident support (historical)** | Support-era 1st/2nd-level B2B troubleshooting (2016–2020); not current on-call rotation. ([WORK_COMP_2]) | weak |

---

<!-- jobfit:prep-claims:gaps -->
## Gaps vs prep shortlist (honest transfer lines)

| Gap | Jobs | Count | Do not claim | Say instead |
|---|---|---:|---|---|
| **AWS** | S1, S2, S4 | 3 | Production AWS ownership | Primary cloud is GCP; IaC patterns transfer |
| **Azure** | S1, S4 | 2 | Azure production | Target learning |
| **Jenkins** | S4 | 1 | Jenkins admin | GitLab CI owner |
| **IAM** | S2 | 1 | AWS IAM in prod | Vault RBAC + AppRole for apps/secrets |
| **OpenTelemetry** | S2 | 1 | OTel in prod | Prometheus/Grafana at 200+ hosts |
<!-- /jobfit:prep-claims:gaps -->

---

## Do not claim (hard stop)

- Production AWS / Azure experience
- AWS IAM policy depth

---

## Quick reference

| Theme | Lead bullet |
|---|---|
| CI/CD | GitLab CI: 45→10 min deploy; Semgrep + ZAP |
| IaC | Terraform + Ansible: 29 resources across GCP/DO |
