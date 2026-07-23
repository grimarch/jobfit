# Personas review (Phase 1)

**Goal:** interview-ready [`personas.md`](../prompts/prep/devops/personas.md) — which 3 jobs to practice on + how to use claims per role.

---

## Prerequisites

Before first `prep-personas draft`:

1. `context.md` exported with `--include-company` (for company names in draft)
2. All starred jobs labeled: `prep_label` ∈ `fit` | `stretch` | `brand-only` | `skip-for-prep`
3. `claims.md` has **`**Reviewed:**`** header (Phase 0c complete)
4. `data/user/devops/input/prep_roles.yaml` exists — copy from `prep_roles.yaml.example` and set S* ids

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
- [ ] **Gaps for this job** match claims.md Gaps table — spot-check AWS/Azure/Jenkins (must be verbatim)
- [ ] No production AWS/Azure claims introduced in Lead from claims
- [ ] Language matches context: S4 DE primary, S1/S2 EN; S4 on-call = historical 2016–2020
- [ ] Mock order matches `mock_order` list in `prep_roles.yaml`
- [ ] Anchors table filled (one-liner per role)
- [ ] Stories to write numbered consistently
- [ ] Later job has company + refnr (not just one-liner)
- [ ] H1 is `# Prep roles (devops)` — not renamed
- [ ] `**Draft** generated:` carries original ISO timestamp (not replaced with CV metadata)
- [ ] No `[CANDIDATE_NAME]` / `[EMAIL]` PII in output
- [ ] Summary table (`| Prep role | Job | Company |`) present
- [ ] `## Mock order` section present with numbered list
- [ ] `## Anchors` table present
- [ ] **JD focus** paraphrases `**JD excerpt:**` only — no invented stack terms

---

## Three files

| File | Meaning |
|---|---|
| `personas.draft.md` | CLI output — throwaway skeleton with deterministic gaps |
| `personas.llm.md` | LLM output — still draft until you verify |
| `personas.md` | **Interview SoT** after verify |

Do not use stories/mock until `personas.md` is **Reviewed**.

---

## `prep_roles.yaml` — required before draft

**Path:** `data/user/devops/input/prep_roles.yaml` (gitignored)
**Example:** `data/user/devops/input/prep_roles.yaml.example`

```bash
cp data/user/devops/input/prep_roles.yaml.example data/user/devops/input/prep_roles.yaml
# Edit: set S* ids, labels, archetypes, mock_order
docker compose exec app jobfit prep-personas draft --role devops --force
```

`prep-personas draft` raises `FileNotFoundError` if `prep_roles.yaml` is absent.

**Fields:**

| Field | Required | Description |
|---|---|---|
| `mock_cycle[].id` | yes | S* id from context.md (e.g. `S1`) |
| `mock_cycle[].label` | yes | Display label in draft (e.g. `Primary`, `Mittelstand`) |
| `mock_cycle[].archetype` | no | Short archetype hint for summary table |
| `mock_cycle[].llm` | no | Per-role hints for `refine` LLM (lead_themes, language, framing, mock_traps_extra) |
| `later[].id` | yes | S* id for jobs to skip in first mock cycle |
| `later[].label` | no | Default: `Later` |
| `later[].reason` | no | One-line note on why deferred |
| `mock_order` | no | List of S* ids in practice order (default: mock_cycle order) |
| `refine` | no | Global hints block appended to PREP CONFIG for the refine LLM |

**LLM hints (`llm:` per role):** passed to `prep-personas refine` as `## PREP CONFIG` in the user prompt. CV and claims.md are authoritative — hints are guidance only and cannot override facts.

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
