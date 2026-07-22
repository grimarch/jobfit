# Claims review (Phase 0c)

**Goal:** interview-ready [`claims.md`](../prompts/prep/devops/claims.md) — what you can prove from CV + honest gap lines.

---

## Start here

### First time (context not ready)

```bash
docker compose exec app jobfit prep-context export \
  --role devops --cv prompts/CV.md \
  --out prompts/prep/devops/context.md
```

1. Open `prompts/prep/devops/context.md`
2. On every `### S*`: set `prep_label` + `why_starred`
3. Re-run export (same command) to keep your edits

Then continue with **Every run** below.

### Every run

```bash
# 1 — machine draft (NOT for interviews)
docker compose exec app jobfit prep-claims draft --role devops --force
# → prompts/prep/devops/claims.draft.md

# 2 — LLM refine (default)
docker compose exec app jobfit prep-claims refine --role devops --force
# → prompts/prep/devops/claims.llm.md

# 2 — manual fallback: chat + prompts/prep/devops/claims_review_prompt.md

# 3 — you verify (~10 min): CV.md + claims.llm.md
#   • 3–5 random ok rows match CV
#   • Vault / Cloud / Python / GitLab look sane
#   • Gaps Jobs/Count unchanged vs draft
#   • Read ## LLM verify notes at bottom

# 4 — promote
cp prompts/prep/devops/claims.llm.md prompts/prep/devops/claims.md
# Set header: **Reviewed:** YYYY-MM-DD · CV: `prompts/CV.md` · context: `prompts/prep/devops/context.md`
```

**Done when** `claims.md` says **Reviewed** and you'd defend every `ok` row. Then → personas → stories → mock.

### Later (maintenance only)

| Situation | Do this |
|---|---|
| Re-starred jobs, CV unchanged | re-export context → `prep-claims draft --role devops --merge` |
| CV edited | full **Every run** again |
| Gap wording only | edit `gap_lines.yaml` in user input dir → `--force` or `--merge` |

```bash
docker compose exec app jobfit prep-claims draft --role devops --merge
# updates Jobs/Count on claims.md only
```

---

## Three files

| File | Meaning |
|---|---|
| `claims.draft.md` | CLI output — throwaway input for LLM |
| `claims.llm.md` | LLM output — still draft until you verify |
| `claims.md` | **Interview SoT** after Step 3 |

Do not use stories/mock until `claims.md` is **Reviewed**.

---

## Appendix

<details>
<summary><strong>What CLI does vs LLM</strong></summary>

**CLI** (`prep-claims draft`): sections from layout YAML, regex-matched Evidence, Gaps Jobs/Count (+ Do not/Say from `gap_lines.yaml` if present).

**LLM** (`prep-claims refine`): fix wrong bullets, split Cloud rows, restore truncated metrics, `[WORK_COMP_N]`, Quick reference, Do not claim, ok/weak. Must not change Gaps Jobs/Count or invent facts.

Env: `PREP_CLAIMS_PROVIDER`, `PREP_CLAIMS_API_KEY`, `PREP_CLAIMS_MODEL` (default haiku when unset). Falls back to `LLM_*`.

Debug: `jobfit prep-claims refine --role devops --print-prompt` or `--dry-run`.

</details>

<details>
<summary><strong>User config (already set for devops)</strong></summary>

| File | Location |
|---|---|
| Layout override | `data/user/devops/input/claims_layout.yaml` |
| Gap honest lines | `data/user/devops/input/gap_lines.yaml` |

Repo examples: [`claims_layout.yaml.example`](../data/user/devops/input/claims_layout.yaml.example), [`gap_lines.yaml.example`](../data/user/devops/input/gap_lines.yaml.example).

Loaded automatically when present (`JOBFIT_USER_DATA_DIR` / Docker secrets path).

</details>

<details>
<summary><strong>Verify checklist (Step 3 detail)</strong></summary>

- [ ] Header → **Reviewed** with date
- [ ] 3–5 random `ok` rows checked against CV
- [ ] Vault, Python, Cloud, GitLab — no classic matcher mistakes
- [ ] Gaps Jobs/Count identical to `claims.draft.md`
- [ ] Do not claim / Gaps lines speakable and honest
- [ ] No AWS/Azure as owned production experience
- [ ] LLM verify notes resolved or reverted

</details>

<details>
<summary><strong>Manual LLM fallback</strong></summary>

If `prep-claims refine` is unavailable or output is poor: new chat, attach `CV.md` + `claims.draft.md`, paste prompt from `claims_review_prompt.md` (below `---`), save as `claims.llm.md`.

</details>

<details>
<summary><strong>No LLM fallback</strong></summary>

Edit `claims.draft.md` by hand (same bar as verify checklist), copy to `claims.md`, set **Reviewed** header.

</details>

<details>
<summary><strong>Old claims.md.bak</strong></summary>

Run fresh `--force` draft. Use `.bak` only as hint for bullet fixes — do not blind-merge.

</details>

---

**See also:** [prep-workflow.md](prep-workflow.md) (full prep cycle) · [prompts/prep/README.md](../prompts/prep/README.md) (all artifact files)
