# Interview prep workflow

Repeatable pipeline for turning JobFit market data into interview-ready material.
Works per **role** (`devops` today; same steps for future roles).

This is **separate from job search scoring**: tier/score ranks vacancies for applications;
prep artifacts rank what you **practice** for interviews.

## Two pipelines

| Pipeline | Purpose | Lives in | When |
|---|---|---|---|
| **JobFit data** | Ingest, classify, enrich, score, star | PostgreSQL + dashboards | Ongoing |
| **Interview prep** | CV truth + starred shortlist → mock-ready content | `prompts/prep/{role}/` | Before active interviewing |

Do **not** use static HTML dashboards or `data/{role}/input/` demo CV for prep truth.
Use live DB via export + `prompts/CV.md` (or role-specific CV path).

## Sources of truth

| What | Path | Rule |
|---|---|---|
| Experience you can defend | `prompts/CV.md` (or `--cv` path) | Only claims backed here |
| Market + starred handoff | `prompts/prep/{role}/context.md` | From `jobfit prep-context export` |
| Human prep verdict | `prep_label`, `why_starred` in context | You edit; merge survives re-export |
| Demo / portfolio input | `data/user/{role}/input/` | Ignore for interview prep |
| Prep claims layout (optional) | `data/user/{role}/input/claims_layout.yaml` | Full replace of repo generic layout |
| Prep gap lines (optional) | `data/user/{role}/input/gap_lines.yaml` | Gaps Do not / Say columns |
| Static dashboards | `dashboards/*.html` | Stale; do not parse |

## File layout (per role)

```
prompts/
  CV.md                          # default CV SoT (override with --cv)
  prep/
    README.md                    # this convention
    devops/
      context.md                 # export: prefs, market, starred (was prep_context.md)
      claims.draft.md            # Phase 0c: CLI machine draft (default prep-claims output)
      claims.llm.md              # optional: LLM-refined draft for review
      claims.md                  # Phase 0c: reviewed SoT after human verify
      personas.md                # Phase 1: prep roles — 3 mock scenarios (S1, S4, …)
      stories.md                 # Phase 2: STAR-style answers DE+EN
      notes.md                   # Phase 3–4: tech depth + DE funnel (pitch, Gehalt)
      drills.md                  # Phase 5: written exercises before mock
    backend/                     # same files when another role is added
      context.md
      ...
```

**Legacy:** `prompts/prep_context.md` at repo root still works — point `--out` at the new path when migrating.

## Automation tiers

### Tier 1 — automated (JobFit CLI today)

| Step | Command / module | Output |
|---|---|---|
| Refresh DB | `jobfit fetch …`, `jobfit classify`, `jobfit enrich` | classifications |
| Fix known mislabels | `scripts/fix_classify_errors.py [--firma NAME] [--apply]` | DB corrections |
| Rebuild UI | `jobfit serve rebuild` | dashboards |
| Export handoff | `jobfit prep-context export --role ROLE --cv PATH --out prompts/prep/ROLE/context.md` | `context.md` |

Export includes: preferences, market snapshot, starred jobs (overlap/gaps vs CV),
`prep_heuristic`, `agency_suspect`, redacted JD excerpts, embedded field glossary.
Re-export **merges** your `prep_label` / `why_starred` by `refnr` (unless `--no-merge`).

### Tier 2 — semi-automated (JobFit CLI + review)

| Step | Command | Output | Human review |
|---|---|---|---|
| Claim → evidence draft | `jobfit prep-claims draft` | `claims.draft.md` — structured sections, CV-matched evidence | — |
| Gaps from shortlist | same + `--context`; refresh counts on SoT | Gaps table (Jobs/Count) on `claims.md` via `--merge` | Step 2 verify; `gap_lines.yaml` |
| Story draft | agent / manual | `stories.md` | Required |
| Prep roles checklist | manual | `personas.md` | Confirm S* choice |

### Tier 3 — manual only

- Star / unstar jobs in the UI
- Fill `prep_label` and `why_starred`
- Verify every claim against CV (no demo CV skills)
- Choose whether to **apply** vs **practice only**
- Mock interview sessions and final pitch wording

## Repeat cycle (checklist)

Run when starting a new search wave or switching role focus.

### A. JobFit data (machine)

1. `jobfit fetch all --role ROLE` (or your usual subset)
2. `jobfit classify --role ROLE` · `jobfit enrich --role ROLE`
3. Star promising jobs in Target Companies UI
4. `jobfit prep-context export \
     --role ROLE \
     --cv prompts/CV.md \
     --out prompts/prep/ROLE/context.md \
     --market-scope sm`

### B. Human shortlist (context.md)

5. For each `### S*`: set `prep_label` (`fit` | `stretch` | `brand-only` | `skip-for-prep`)
6. Fill `why_starred` (why starred + prep caveats: on-call, onsite, gaps)
7. Re-export to refresh machine fields without losing human fields

### C. Claims (Phase 0c)

8. `jobfit prep-claims draft --role ROLE --force` → `claims.draft.md`  
9. Follow **[prep-claims-review.md](prep-claims-review.md)** — `draft` → `refine` → verify → `claims.md`  
10. Gap refresh only: `jobfit prep-claims draft --role ROLE --merge`

### D. Practice material

10. `personas.md` — 3 prep roles from fit/stretch (different archetypes)
11. `stories.md` — 8–10 stories from claims (DE for HR, EN for tech)
12. `notes.md` — must-defend topics + recurring starred gaps + 2-min pitch
13. `drills.md` — 2 design + 2 debug written answers for primary prep role (S1)

### E. Mock

14. Live mock on primary prep role (`fit`, e.g. S1) only after drills
15. Update stories/notes from mock feedback

## Phase map (artifacts)

| Phase | Artifact | Ready when |
|---|---|---|
| 0a | `context.md` | export done |
| 0b | human fields in `context.md` | all starred labeled |
| 0c | `claims.md` | **Reviewed** — [prep-claims-review.md](prep-claims-review.md) |
| 1 | `personas.md` | 3 prep roles + anchors from claims |
| 2 | `stories.md` | 8–10 stories DE+EN |
| 3 | `notes.md` (depth) | core stack + starred gaps covered |
| 4 | `notes.md` (funnel) | pitch + Gehalt + Fragen an uns |
| 5 | `drills.md` | written exercises done |
| Mock | session | Definition of ready below |

## Definition of ready (before mock)

- [ ] `context.md` current; starred tagged fit/stretch/skip
- [ ] `claims.md` complete — CV.md only, no demo CV leakage
- [ ] 3 prep roles with anonymized excerpts (in context or personas.md)
- [ ] 8 STAR-style stories DE+EN
- [ ] Pitch + salary/availability phrasing
- [ ] Deep dive on 5 core topics + recurring gaps from fit/stretch starred
- [ ] At least 2 debug + 2 design written drills
- [ ] List of skills you **do not** claim (stretch / gap honesty)

## Artifact reference (what each file is)

Full table: [prompts/prep/README.md](../prompts/prep/README.md).

| File | Question it answers | JobFit command |
|---|---|---|
| `context.md` | Which starred jobs, market gaps, overlap **per job**? | `prep-context export` |
| `claims.md` | What can I **prove** from CV? | [prep-claims-review.md](prep-claims-review.md) |
| `personas.md` | Which 3 jobs / prep roles do I practice on? | — (manual) |
| `stories.md` | How do I tell the story in an interview? | — (manual / agent) |
| `notes.md` | Depth + HR pitch + Gehalt | — (manual) |
| `drills.md` | Written rehearsal before mock | — (manual) |

**Important:** `prep-claims draft` reads **CV** for the claims table and **context** only for the Gaps section. It does not replace reading `context.md` per vacancy.

## CLI examples

```bash
# 1. Export market + starred handoff
jobfit prep-context export \
  --role devops \
  --cv prompts/CV.md \
  --out prompts/prep/devops/context.md \
  --jd-excerpt-chars 400 \
  --market-scope sm

# 2. Claims — draft + refine → see prep-claims-review.md
jobfit prep-claims draft --role devops --force
jobfit prep-claims refine --role devops --force

# Dry-run counts
jobfit prep-context export --role devops --dry-run
jobfit prep-claims draft --role devops --dry-run
```

When `--context` is omitted, `prep-claims draft` uses `prompts/prep/{role}/context.md` if the file exists; otherwise writes **claims only** (no Gaps section).

Honest lines in the Gaps table: optional cache `data/user/{role}/input/gap_lines.yaml` (loaded in draft). Use `--merge` to refresh **Jobs/Count** without rewriting claim sections.

**Layout:** default `jobfit/prep_context/layouts/{role}.yaml` (generic, skill-only). Optional override: copy [claims_layout.yaml.example](../data/user/devops/input/claims_layout.yaml.example) → `data/user/{role}/input/claims_layout.yaml` for CV-specific row matching (full replace).

## Using an AI agent

Attach to the chat (do not grant DB access):

1. `prompts/CV.md`
2. `prompts/prep/{role}/context.md`
3. Optionally `claims.md`, `personas.md`

Ask the agent to **not** recompute market stats or parse HTML dashboards.
Human fields in context are authoritative for prep intent.

## Effort estimate (after Tier 1 exists)

| Step | First time | Refresh (3–6 months) |
|---|---|---|
| Export + label starred | 1–2 h | 20–40 min |
| claims.draft.md + review | 1–2 h review | ~15 min re-draft + review if CV unchanged |
| personas.md | 30 min | 15 min |
| stories.md | 4–8 h | 2–4 h |
| notes + drills | 3–5 h | 1–2 h |
| Mock | 1–2 sessions | 1 session |

## Related

- Per-file guide: [prompts/prep/README.md](../prompts/prep/README.md)
- **Claims review (Step 1 LLM + Step 2 verify):** [prep-claims-review.md](prep-claims-review.md)
- Field glossary: embedded in exported `context.md` (`## Field reference`)
- Export implementation brief: [prompts/prep_context_export_agent.md](../prompts/prep_context_export_agent.md)
