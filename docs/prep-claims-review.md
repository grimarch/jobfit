# Reviewing `prep-claims draft` (Phase 0c)

How to turn CLI output into interview-ready `claims.md`.

**Parent workflow:** [prep-workflow.md](prep-workflow.md) · **File roles:** [prompts/prep/README.md](../prompts/prep/README.md)

## What the draft is (and is not)

`jobfit prep-claims draft` writes a **draft**, not a source of truth.

| | Draft (after CLI) | Reviewed (`claims.md` SoT) |
|---|---|---|
| Safe for interviews | **No** | **Yes** |
| Header | `**Draft** generated: …` | `**Reviewed:** YYYY-MM-DD …` |
| Claims table | interview sections + CV-matched bullets (`—` where thin) | skill → **best** bullet you verified |
| Gaps table | Jobs/Count from context; Do not/Say empty unless YAML | honest lines in **your** wording |
| Structure | **Stable** sections (layout YAML) | optional Quick reference fill-in |

### What CLI reproduces reliably

- Interview-oriented **sections** from role layout (`jobfit/prep_context/layouts/{role}.yaml`, or user override `data/user/{role}/input/claims_layout.yaml`)
- Gaps table: Jobs, Count, **Do not claim**, **Say instead** (latter two empty unless `gap_lines.yaml`)

### What CLI does **not** do (human or LLM after Pass 1)

- Pick the **best** bullet when several match (e.g. Vault ≠ Terraform bullet)
- Preserve metrics truncated at 220 chars (`45→10`, `200+ hosts`)
- Group claims by interview theme
- Soft skills, languages, certs, “do not claim” list
- Market-only gaps not present in any starred row

---

## Pipeline overview

```text
context.md (prep_label set) ──┐
CV.md ────────────────────────┼──► prep-claims draft ──► claims.md (DRAFT)
                              │
                              └──► Pass 1–4 review ───► claims.md (REVIEWED)
                                         │
                                         └──► stories.md, notes.md, drills.md
```

Do **not** start stories or mock while the file still says `**Draft**`.

---

## Step 0 — Before running draft

| Step | Who | Action |
|---|---|---|
| 0.1 | CLI | `jobfit prep-context export … --out prompts/prep/{role}/context.md` |
| 0.2 | You | Set `prep_label` and `why_starred` on every `### S*` |
| 0.3 | CLI | Re-export to merge human fields |

Gaps in the draft depend on `prep_label`. Jobs marked `skip-for-prep` are excluded (default: fit, stretch, brand-only).

---

## Step 1 — Generate draft

```bash
# Optional: keep last reviewed copy before overwrite
cp prompts/prep/devops/claims.md prompts/prep/devops/claims.reviewed.bak

jobfit prep-claims draft \
  --role devops \
  --cv prompts/CV.md \
  --context prompts/prep/devops/context.md \
  --out prompts/prep/devops/claims.md \
  --force

# Counts only, no write:
jobfit prep-claims draft --role devops --dry-run
```

---

## Pass 1 — Fact check (you, ~15–20 min, no LLM)

Open **only** `prompts/CV.md` and the draft `claims.md`.

| Check | Fix |
|---|---|
| Wrong bullet (e.g. Vault → Terraform/GCP text) | Replace Evidence with the correct CV bullet |
| Same bullet reused for unrelated skills | Assign a distinct bullet per skill |
| Evidence ends with `...` and drops metrics | Add key numbers (deploy time, host count, resource count) |
| Skill marked `ok` but only skills-list support | Move to **weak** or delete row |
| Row you will not defend in interview | Delete |

**Pass 1 done:** every `ok` row is one bullet you verified in CV.

Common matcher mistakes to scan for:

- **HashiCorp Vault** → must be AppRole / Agent / GrimWaves bullet, not Terraform stack bullet
- **Python** → prefer GrimWaves/FastAPI/221 tests over support-era script savings alone
- **MySQL** → troubleshooting only → usually **weak**, not core DevOps claim
- **GitLab CI** → you may need **two** rows (LMS deploy + package pipeline at prior employer)

---

## Pass 2 — Gaps table (you; LLM optional for wording)

| Part | Who |
|---|---|
| Skill / Jobs / Count columns | CLI — refresh with `--merge` (auto on **Reviewed** file) |
| **Do not claim** / **Say instead** | **You** (Pass 2); optional `gap_lines.yaml` |
| Extra gaps from market snapshot (not in starred) | **You** — add 1–2 rows manually if needed |

**LLM allowed:** rephrase Honest line shorter or DE/EN tone.

**LLM forbidden:** invent experience, upgrade gaps to claims, add AWS/Azure ownership.

Optional repeat drafts: copy [gap_lines.yaml.example](../data/user/devops/input/gap_lines.yaml.example) to `data/user/{role}/input/gap_lines.yaml` after Pass 2 to preserve honest lines across `--force` re-runs.

Optional layout override: [claims_layout.yaml.example](../data/user/devops/input/claims_layout.yaml.example) → `data/user/{role}/input/claims_layout.yaml` when generic repo layout needs CV-specific rows (two GitLab lines, Vault exclude, certs patterns). Without it, draft uses generic `jobfit/prep_context/layouts/{role}.yaml`.

Safe prompt:

> Using only prompts/CV.md, rewrite the Honest line column in the Gaps table. Do not add skills or experience not in the CV.

---

## Pass 3 — Interview structure (LLM assist; you approve)

Optional. Improves readability before mock; does not add facts.

**LLM may** (attach reviewed Pass 1–2 table + CV.md):

- Group `ok` rows (CI/CD, IaC, observability, …)
- Add **Quick reference**: theme → lead bullet + metric
- Expand **Do not claim** from `weak` + gaps + demo CV rule
- Add factual rows from CV only (languages, B2 cert, RH135) — no new tech claims

**LLM may not:**

- New bullets, metrics, or employers
- Change `ok`/`weak` without your approval
- Pull from `data/user/{role}/input/CV_*.md`

You approve or revert every structural change.

---

## Pass 4 — Freeze reviewed

1. Replace draft header with:

   ```markdown
   **Reviewed:** YYYY-MM-DD · CV: `prompts/CV.md` · context: `prompts/prep/devops/context.md` (as-of from export header)
   ```

2. Complete [Definition of done](#definition-of-done) below.

3. Optional: keep `claims.reviewed.YYYYMMDD.md` as snapshot; treat `claims.md` as current SoT.

---

## Who does what (summary)

| Task | CLI | You | LLM |
|---|---|---|---|
| Starred jobs, market, per-job gaps | `prep-context export` | `prep_label`, `why_starred` | — |
| Draft skill → bullet | `prep-claims draft` | Pass 1 fixes | ❌ do not draft bullets |
| Gaps union + counts | `prep-claims draft` | Pass 2 honest lines | ✏️ rephrase only |
| Grouping, quick reference | — | approve | ✅ after Pass 1 |
| STAR stories | — | final | ✅ from **reviewed** claims only |
| Mock / pitch | — | ✅ | practice only |

**Rule:** LLM runs **after** Pass 1, or on **wording** only — never as sole fact checker.

---

## Definition of done

Phase 0c is complete when:

- [ ] Header says **Reviewed** with date (not **Draft**)
- [ ] Every `ok` row points to a CV bullet you checked manually
- [ ] No duplicate wrong bullet across unrelated skills (Vault/GitLab/Python/etc.)
- [ ] Key metrics present for your lead stories (deploy time, scale, TF resource count, …)
- [ ] `weak` skills are not used as primary interview claims
- [ ] Gaps honest lines are speakable and honest
- [ ] **Do not claim** list is explicit (demo CV, cloud you do not operate, etc.)
- [ ] CV has not changed since review — or Pass 1 was re-run after CV edit

Then proceed to [personas.md](../prompts/prep/devops/personas.md) → stories → notes → drills → mock.

---

## When to re-run draft

| Event | Action |
|---|---|
| New starred / re-label only, same CV | Re-export context → `prep-claims draft --merge` (or auto if **Reviewed**) |
| CV.md edited | Full Pass 1–4 |
| New role | New folder `prompts/prep/{role}/`, both CLI commands with `--role` |
| Lost reviewed file | Re-draft + full review; old `.bak` is hint only, not SoT |

---

## Using a previous manual/LLM version

An older hand-written `claims.md.bak` is a **review checklist**, not something to merge blindly.

1. Run fresh `prep-claims draft`
2. Pass 1: diff against `.bak` — copy **bullet fixes** only where CLI is wrong
3. Pass 2: keep CLI gaps table (counts); merge better honest lines from `.bak` if you prefer them
4. Pass 3: optionally reuse grouping/quick reference from `.bak` if still accurate vs CV

---

## Quality gate

| Skip review | With this pipeline |
|---|---|
| Wrong bullet under pressure | Pass 1 catches before mock |
| Over-claiming AWS/Azure | Gaps + Do not claim |
| Reinvent file every cycle | draft + 20–40 min review |
| LLM invents in stories | stories only from reviewed `ok` rows |

**Do not** attach draft `claims.md` to an agent for story generation until Pass 4 is done.
