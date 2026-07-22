# Personas review (Phase 1)

**Goal:** interview-ready [`personas.md`](../prompts/prep/devops/personas.md) — which 3 jobs to practice on + how to use claims per role.

---

## Prerequisites

Before first `prep-personas draft`:

1. `context.md` exported with `--include-company` (for company names in draft)
2. All starred jobs labeled: `prep_label` ∈ `fit` | `stretch` | `brand-only` | `skip-for-prep`
3. `claims.md` has **`**Reviewed:**`** header (Phase 0c complete)

---

## Every run

```bash
# 1 — machine draft (NOT for mock interviews)
docker compose exec app jobfit prep-personas draft --role devops --force
# → prompts/prep/devops/personas.draft.md

# 2 — LLM refine
docker compose exec app jobfit prep-personas refine --role devops --force
# → prompts/prep/devops/personas.llm.md

# 2 — manual fallback: chat + prompts/prep/devops/personas_review_prompt.md

# 3 — you verify (~10 min): see checklist below

# 4 — promote
cp prompts/prep/devops/personas.llm.md prompts/prep/devops/personas.md
# Set header: **Reviewed:** YYYY-MM-DD
```

**Note:** Docker mounts `./prompts` but not `./jobfit`. After code changes, rebuild:

```bash
docker compose build app
```

---

## Verify checklist (~10 min)

- [ ] 3 mock roles (fit + stretch, different archetypes) + 1 Later
- [ ] **Gaps for this job** match claims.md Gaps table — spot-check AWS/Azure/Jenkins
- [ ] No production AWS/Azure claims introduced in Lead from claims
- [ ] Language matches context: S4 DE primary, S1/S2 EN
- [ ] Mock order: fit first
- [ ] Anchors table filled (one-liner per role)
- [ ] Stories to write numbered consistently
- [ ] Later job has short entry, not a full block

---

## Three files

| File | Meaning |
|---|---|
| `personas.draft.md` | CLI output — throwaway skeleton with deterministic gaps |
| `personas.llm.md` | LLM output — still draft until you verify |
| `personas.md` | **Interview SoT** after verify |

Do not use stories/mock until `personas.md` is **Reviewed**.

---

## Optional: custom role selection (`prep_roles.yaml`)

**Default path:** `data/user/devops/input/prep_roles.yaml` (gitignored)
**Example:** `data/user/devops/input/prep_roles.yaml.example`

```bash
cp data/user/devops/input/prep_roles.yaml.example data/user/devops/input/prep_roles.yaml
# Edit: set S* ids, labels, archetypes, mock_order
docker compose exec app jobfit prep-personas draft --role devops --force
```

**Fields:**

| Field | Required | Description |
|---|---|---|
| `mock_cycle[].id` | yes | S* id from context.md (e.g. `S1`) |
| `mock_cycle[].label` | yes | Display label in draft (e.g. `Primary`, `Mittelstand`) |
| `mock_cycle[].archetype` | no | Short archetype hint for summary table |
| `later[].id` | yes | S* id for jobs to skip in first mock cycle |
| `later[].label` | no | Default: `Later` |
| `later[].reason` | no | One-line note on why deferred |
| `mock_order` | no | List of S* ids in practice order (default: mock_cycle order) |

Without YAML: draft auto-selects fit first, then stretch (up to 3); brand-only → Later.

---

## Maintenance

| Situation | Do this |
|---|---|
| context.md or claims.md changed | re-run `draft --force` + `refine --force` |
| Only mock order changed | edit `prep_roles.yaml`, re-run `draft --force` |
| Promote to SoT | `cp personas.llm.md personas.md` + `**Reviewed:**` header |

---

## Dry-run (no API, validate inputs)

```bash
docker compose exec app jobfit prep-personas draft --role devops --dry-run
docker compose exec app jobfit prep-personas refine --role devops --dry-run
```

---

**See also:** [prep-workflow.md](prep-workflow.md) (full cycle) · [prompts/prep/README.md](../prompts/prep/README.md) (artifacts) · [prep-claims-review.md](prep-claims-review.md) (Phase 0c)
