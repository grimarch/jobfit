# Prep roles (devops)

**Draft** generated: TIMESTAMP
**Context source:** `tests/fixtures/prep/devops/context_mini.md`
**Claims source:** `tests/fixtures/prep/devops/claims_mini.md`
**Prep roles config:** `auto`

> Machine draft — not for mock interviews. Run `prep-personas refine` then human verify.

**Field guide:** [personas.example.md](personas.example.md) · Proof: [claims.md](claims.md)

---

<!-- jobfit:prep-personas:llm-input -->

| Prep role | Job | Company | prep_label | Archetype | Primary gaps |
|---|---|---|---|---|---|
| Primary | S1 — DevOps Engineer | TestCo | fit | startup / AI/SaaS | AWS, Azure |
| Stretch | S4 — Cloud Engineer | HostingCo | stretch | mittelstand / Cloud Hosting | AWS, Azure, Jenkins |
| Stretch 2 | S2 — Platform Engineer | PlatCo | stretch | startup / AI/Enterprise SaaS | AWS, IAM, OpenTelemetry |

## Mock order

1. **S1** (Primary) — fit · startup / AI/SaaS
2. **S4** (Stretch) — stretch · mittelstand / Cloud Hosting
3. **S2** (Stretch 2) — stretch · startup / AI/Enterprise SaaS

---

## S1 — Primary (startup / AI/SaaS)

**Company:** TestCo
**prep_label:** fit · **refnr:** mini-001

**JD focus:** _TODO — refine from jd_excerpt_

**Lead from claims:** _TODO — refine: 3–5 ok claims / Quick reference themes_

**Gaps for this job:**
- **AWS** — Do not claim: Production AWS ownership. Say: Primary cloud is GCP; IaC patterns transfer
- **Azure** — Do not claim: Azure production. Say: Target learning for customer Azure JDs

**Mock traps:** _TODO — refine: Do not claim + JD-specific_

**Language:** _TODO — refine from context: EN_

**Stories to write (Phase 2):** _TODO — refine: numbered story topics_

---

## S4 — Stretch (mittelstand / Cloud Hosting)

**Company:** HostingCo
**prep_label:** stretch · **refnr:** mini-004

**JD focus:** _TODO — refine from jd_excerpt_

**Lead from claims:** _TODO — refine: 3–5 ok claims / Quick reference themes_

**Gaps for this job:**
- **AWS** — Do not claim: Production AWS ownership. Say: Primary cloud is GCP; IaC patterns transfer
- **Azure** — Do not claim: Azure production. Say: Target learning for customer Azure JDs
- **Jenkins** — Do not claim: Jenkins admin. Say: GitLab CI owner — stages, gates, child pipelines

**Mock traps:** _TODO — refine: Do not claim + JD-specific_

**Language:** _TODO — refine from context: DE B1 / on-call flag_

**Stories to write (Phase 2):** _TODO — refine: numbered story topics_

---

## S2 — Stretch 2 (startup / AI/Enterprise SaaS)

**Company:** PlatCo
**prep_label:** stretch · **refnr:** mini-002

**JD focus:** _TODO — refine from jd_excerpt_

**Lead from claims:** _TODO — refine: 3–5 ok claims / Quick reference themes_

**Gaps for this job:**
- **AWS** — Do not claim: Production AWS ownership. Say: Primary cloud is GCP; IaC patterns transfer
- **IAM** — Do not claim: AWS IAM in prod. Say: Vault RBAC + AppRole for apps/secrets
- **OpenTelemetry** — Do not claim: OTel in prod. Say: Prometheus/Grafana at 200+ hosts

**Mock traps:** _TODO — refine: Do not claim + JD-specific_

**Language:** _TODO — refine from context: EN_

**Stories to write (Phase 2):** _TODO — refine: numbered story topics_

---

## Anchors

| Job | One-line anchor |
|---|---|
| S1 | _TODO — refine_ |
| S4 | _TODO — refine_ |
| S2 | _TODO — refine_ |

<!-- /jobfit:prep-personas:llm-input -->

---

## How this file is used

- `prep-personas refine` reads content between llm-input markers.
- Human promotes `personas.llm.md` → `personas.md` after verify.
- See docs/prep-personas-review.md.

<!-- auto-selection: mock_cycle from prep_label∈fit,stretch (≤3); later from brand-only/skip-for-prep -->
