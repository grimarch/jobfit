# Screenshots

Capture checklist for the main README. Commit PNGs here; paths are referenced from `README.md`.

## Required (3)

Long pages don't have to fit one screenshot — capture as many scrolled sections as needed and
suffix extras `-1`, `-2`, … (e.g. `skills.png`, `skills-1.png`, `skills-2.png`). Reference every
file you add in the main README's Screenshots section.

| File | URL | What to show |
|---|---|---|
| `targets.png` | http://localhost:8888/ | Tier tabs (Dreamjob / CV Builder / …), a few job rows, action buttons (CV, AS, PRV) |
| `skills.png` (+ `-1`, `-2`, …) | http://localhost:8888/skills | Top skills chart, stage comparison, methodologies/practices, geography |
| `cv-gap.png` (+ `-1`, …) | http://localhost:8888/cv | Gaps/strengths, market requirements, co-occurring skills, top similar jobs |

## Optional (1–2)

| File | URL | When useful |
|---|---|---|
| `listings.png` | http://localhost:8888/listings | Shows multi-source ingestion breadth |
| `cv-preview.png` | `/api/cv/{refnr}/preview?role=devops` | Generated resume HTML — **anonymize PII first** |

## How to capture

1. Start the stack with real classified data:
   ```bash
   docker compose up -d
   # open http://localhost:8888
   ```

2. Browser width **1280px** (DevTools → responsive mode). Full-page or viewport — pick what reads best.

3. Save as PNG into this directory with the exact filenames above.

4. Compress before commit (keep each file under ~300 KB):
   ```bash
   # optional, if pngquant is installed
   pngquant --quality=65-85 docs/screenshots/*.png --ext .png --force
   ```

## Privacy

- OK in screenshots: company names, job titles, public market stats.
- Redact or avoid: your name, email, phone, photo, exact salary expectations.
- For `cv-preview.png`: use a generated CV for a random vacancy, or blur the header block.

## Tools

- **Firefox / Chrome** — DevTools → ⋮ → "Capture screenshot" / full-page extensions
- **Flameshot** / **Spectacle** — region capture on Linux
- **macOS** — Cmd+Shift+4 (region)
