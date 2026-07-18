# JobFit

![Python](https://img.shields.io/badge/python-3.12+-blue?logo=python&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white)


A self-hosted, configurable job-search platform — aggregate vacancies from multiple sources, classify them with LLMs, and turn the data into dashboards, gap analysis, and tailored application documents.

Built as a portfolio project to showcase end-to-end ownership: data pipelines, containerized deployment, database operations, and a production-style web service you can actually run day-to-day.

## 📋 Project Overview

JobFit answers a practical question: *what does the job market in my target segment actually look like right now, and where do I fit?*

It pulls listings from public APIs and ATS feeds, normalizes them into PostgreSQL, enriches with LLM + regex classification, and serves interactive dashboards on top. Beyond analytics, it also generates per-job CVs and cover letters — because market research and job applications tend to happen in the same workflow.

**Status:** Active / personal tooling  
**Primary Focus:** Data pipelines, containerized ops, PostgreSQL, FastAPI  
**Shipped today:** 1 role (`devops`), 1 market (Germany)  
**Roadmap:** more roles and markets  
**DIY today:** add your own role module or fetcher module — no need to wait, see [Extending](#-extending)

> **One role, one market — for now.** Out of the box you get DevOps/SRE/Platform Engineer tracking with Germany-focused sources. More roles and markets are planned, but you can add your own role module or fetcher module today if your segment isn't covered yet.

## 📸 Screenshots

> Place captured images in `docs/screenshots/` — see [capture guide](docs/screenshots/README.md).

### Target Companies

![Target companies dashboard — tiered shortlist with CV and cover letter actions](docs/screenshots/targets.png)

*Tiered shortlist (Dreamjob / CV Builder / Easy Win / Skip) with per-job stage/mode breakdown and action buttons.*

### Skills Analysis

![Top 20 skills and stage comparison — start](docs/screenshots/skills.png)

![Stage comparison heatmap and methodologies/practices](docs/screenshots/skills-1.png)

![Full skills table and geography breakdown](docs/screenshots/skills-2.png)

*Top skills across all product companies, compared by company stage, plus methodologies/practices and geographic spread.*

### CV Gap Analysis

![Gaps & strengths, market requirements panel](docs/screenshots/cv-gap.png)

![Co-occurring requirements heatmap and top similar jobs](docs/screenshots/cv-gap-1.png)

*Your profile vs. market demand — gaps/strengths, market requirements, co-occurring skills, and top similar jobs.*

### Listings by Platform *(optional)*
![Vacancies grouped by ATS source](docs/screenshots/listings.png)

## 🚀 Features

### Market Intelligence
- **Multi-source ingestion** — Bundesagentur API, jobhive (13 ATS platforms), Softgarden feeds, Ever Jobs sidecar
- **LLM classification** — company type (product / agency / enterprise), industry, tech stack signals
- **Regex enrichment** — work mode, seniority, language requirements, salary parsing
- **Closed-job tracking** — detects vacancies that disappeared from feeds
- **Brand tiering** — ranks companies into target tiers for focused job search

### Dashboards
- **Target companies** (`/`) — tiered shortlist with star/read tracking
- **Skills chart** (`/skills`) — in-demand hard skills across product companies
- **Listings** (`/listings`) — all vacancies grouped by ATS platform
- **CV gap analysis** (`/cv`) — your profile vs. market demand

### Application Tools
- **CV extract** — structured profile from your resume (PDF / MD / TXT)
- **CV generate** — LLM-tailored resume per vacancy, rendered to PDF
- **Anschreiben** — DIN 5008 cover letters, tone adapted to company stage (startup / Mittelstand / enterprise)
- **PII anonymization** — personal data stripped before LLM calls, restored locally after generation

### Platform
- **CLI + Web API** — same logic via `jobfit` commands or FastAPI endpoints
- **Hot dashboard reload** — rebuild caches without restarting the server (~50s, zero downtime)
- **Provider-agnostic LLM** — Anthropic, OpenAI-compatible APIs, Ollama; split models per task
- **Role modules** — one file in `jobfit/roles/` per job title track (skills, title patterns, CV templates)
- **Fetcher modules** — add sources for new markets or platforms without touching core logic

## 🏗 Architecture

```mermaid
flowchart TB
    subgraph sources["Data Sources"]
        BA["Bundesagentur für Arbeit API"]
        JH["jobhive Parquet (13 ATS)"]
        SG["Softgarden feeds"]
        EJ["Ever Jobs sidecar"]
    end

    subgraph compose["Docker Compose"]
        EJSVC["everjobs :3001"]
        APP["jobfit app :8888"]
        DB[("PostgreSQL 16")]
    end

    subgraph pipeline["Processing Pipeline"]
        FETCH["fetch"]
        CLOSE["mark-closed"]
        CLS["classify (LLM)"]
        ENR["enrich (regex)"]
        BRD["brands (LLM)"]
        DASH["dashboards + cache"]
    end

    BA & JH & SG --> FETCH
    EJ --> EJSVC --> FETCH
    FETCH --> DB
    CLOSE --> DB
    CLS --> DB
    ENR --> DB
    BRD --> DB
    DB --> DASH
    DASH --> APP
```

**How it flows:** fetchers write normalized jobs to PostgreSQL → `classify` / `enrich` / `brands` augment metadata → dashboards pre-render HTML at startup and on rebuild → FastAPI serves cached pages with ETag support and async document generation.

## 🛠 Technology Stack

### Application
- **Python 3.12** — runtime
- **Click** — CLI framework
- **FastAPI + Uvicorn** — web server and REST API
- **SQLAlchemy 2 + Alembic** — ORM and schema migrations
- **Jinja2 + WeasyPrint** — HTML templates and PDF rendering
- **matplotlib / plotly / seaborn** — dashboard charts
- **loguru** — structured logging

### Data & AI
- **PostgreSQL 16** — primary datastore
- **pandas + pyarrow** — Parquet ingestion (jobhive)
- **Provider-agnostic LLM client** — Anthropic, OpenAI-compatible, Ollama
- **fastapi-cache2** — in-memory response cache

### DevOps & Infrastructure
- **Docker** — application containerization
- **Docker Compose** — multi-service orchestration (app + db + everjobs sidecar)
- **uv** — lockfile-based dependency management
- **Health checks** — `pg_isready` for PostgreSQL, TCP probe for sidecar
- **Backup scripts** — `pg_dump` with retention policy
- **pytest** — unit and integration tests

## 📡 Data Sources

Bundled fetchers today are Germany-heavy; the pipeline itself is source-agnostic — add a fetcher module to cover another market.

| Source | Coverage | How |
|---|---|---|
| **Bundesagentur für Arbeit** | Germany (nationwide) | Public REST API |
| **jobhive** | Multi-region ATS (13 platforms: Ashby, Greenhouse, Personio, Workday, …) | Parquet snapshots, 24h local cache |
| **Softgarden** | Germany (~60 curated companies) | Public `jobs.feed.json` per slug |
| **Ever Jobs** | Germany (GermanTechJobs, BerlinStartupJobs, Adzuna) | Self-hosted sidecar container |

## 🔧 Installation & Setup

### Prerequisites
- Docker + Docker Compose
- LLM API key (needed for `classify`; optional for exploring fetch/dashboard flow)

### Docker (recommended)

1. **Configure environment:**
```bash
cp .env.example .env          # set LLM_API_KEY and POSTGRES_PASSWORD
cp data/user/devops/input/CV_devops.md.example data/user/devops/input/CV_devops.md
cp data/user/devops/input/brands_prompt.txt.example data/user/devops/input/brands_prompt.txt
cp data/user/devops/input/scoring.yaml.example data/user/devops/input/scoring.yaml
cp data/user/devops/input/anschreiben_profile.md.example data/user/devops/input/anschreiben_profile.md   # optional, used by `jobfit cv anschreiben`
```

2. **Bootstrap data** (empty DB won't pass startup checks):
```bash
docker compose up -d db
docker compose run --rm app jobfit fetch all --role devops
docker compose run --rm app jobfit classify --role devops
```

3. **Start the app:**
```bash
docker compose up -d --build    # → http://localhost:8888
```

One-off CLI tasks reuse the same image without starting the server:
```bash
docker compose run --rm app jobfit fetch all --role devops
```

### Local development

```bash
uv sync
export DATABASE_URL=postgresql://jobfit:jobfit@localhost:5432/jobfit
uv run alembic upgrade head
uv run jobfit fetch all && uv run jobfit classify && uv run jobfit dashboard all
```

## 🐳 Deployment & Operations

### Container stack

| Service | Image | Role |
|---|---|---|
| `db` | `postgres:16-alpine` | Primary datastore (`postgres_data` volume) |
| `app` | `python:3.12-slim` + `uv` | CLI + FastAPI server |
| `everjobs` | `ghcr.io/ever-jobs/ever-jobs:latest` | Job aggregator sidecar |

`docker-compose.yml` handles service DNS, health checks, and bind-mounts `./data` + `./logs` for persistence outside containers.

### Boot sequence

On every container start, `docker-entrypoint.sh`:

1. Runs `alembic upgrade head`
2. Migrates SQLite → PostgreSQL once (if `data/jobfit.db` exists)
3. Validates DB prerequisites via `python -m jobfit.startup`
4. Starts `uvicorn` on port `8888`

### Day-2 operations

```bash
# Full refresh: fetch → mark-closed → rebuild dashboards
docker compose exec app jobfit serve sync

# New unclassified jobs appeared?
docker compose exec app jobfit classify --role devops
docker compose exec app jobfit enrich --role devops
docker compose exec app jobfit brands --role devops

# Zero-downtime dashboard refresh (~50s)
docker compose exec app jobfit serve rebuild
```

`classify` and `brands` need an LLM API key and stay outside automated sync — by design, since they cost money.

### Backups

```bash
docker compose up -d db
./scripts/backup.sh              # pg_dump → backups/jobfit-YYYYMMDD-HHMM.dump
./scripts/backup.sh --data       # + tarball of data/devops (CV artifacts)
./scripts/backup.sh --keep-days 7
```

Restore:
```bash
docker compose exec -T db pg_restore -U jobfit -d jobfit --clean --if-exists \
  < backups/jobfit-YYYYMMDD-HHMM.dump
```

## 📂 Project Structure

```bash
jobfit/
├── cli.py                  # Click entry point (jobfit ...)
├── app.py                  # FastAPI server + ETag middleware
├── sync.py                 # fetch → close → enrich → dashboards
├── classify.py             # LLM job classification
├── enrich.py               # regex metadata enrichment
├── brands.py               # company brand tiering
├── startup.py              # boot-time DB validation
├── db/                     # SQLAlchemy models + session
├── fetchers/               # jobhive, bundesagentur, softgarden, everjobs
├── dashboards/             # analysis, skills, targets, listings, CV gap
├── cv/                     # extract, generate, PDF render
├── anschreiben/            # cover letter generation
└── roles/                  # role definitions (skills, title patterns)

alembic/                    # database migrations
scripts/                    # backup, SQLite→PG migration, data utilities
data/                       # raw caches, role input/output (secrets gitignored)
docker-compose.yml
Dockerfile
docker-entrypoint.sh
```

## ⌨️ CLI Reference

```bash
# Data collection
jobfit fetch all              # all sources
jobfit fetch jobhive          # jobhive only (13 ATS platforms)
jobfit fetch softgarden       # softgarden feeds
jobfit fetch ba               # Bundesagentur only
jobfit fetch everjobs         # Ever Jobs sidecar

# Processing
jobfit classify               # LLM classification (manual, API cost)
jobfit enrich                 # work_mode, seniority, salary, language
jobfit brands                 # known IT brand tiers (manual, API cost)
jobfit mark-closed            # flag jobs removed from feeds

# Output
jobfit dashboard all          # rebuild all dashboards
jobfit sync                   # full local cycle
jobfit serve sync             # full cycle for Docker

# Application documents
jobfit cv extract <path>      # build cv_profile.json
jobfit cv generate <refnr>    # tailored resume PDF
jobfit cv anschreiben <refnr> # cover letter PDF (DIN 5008)
```

All commands accept `--role` (default: `devops`). Handy flags: `--dry-run`, `--limit N`, `--audit`.

## 🌐 Web API

FastAPI on port **8888**:

| Group | Endpoints |
|---|---|
| **Dashboards** | `/` (targets), `/skills`, `/listings`, `/cv` |
| **CV** | `POST /api/cv/{refnr}/generate` · `GET …/status` · `GET …/download` · `GET …/preview` |
| **Anschreiben** | `POST /api/anschreiben/{refnr}/generate` · same status/download/preview pattern |
| **Job state** | `POST/DELETE /api/starred/{refnr}` · `POST/DELETE /api/read/{refnr}` |
| **Cache** | `POST /api/cache/rebuild` — hot-reload dashboards without restart |

## ⚙️ Configuration

Copy `.env.example` → `.env`:

| Variable | Purpose |
|---|---|
| `LLM_API_KEY` / `LLM_PROVIDER` | Primary LLM for classify, brands |
| `CV_MODEL` / `CV_PROVIDER` | Separate model for CV/Anschreiben (optional) |
| `POSTGRES_PASSWORD` | Database credentials |
| `CV_ANONYMIZE_LLM` | Strip PII before LLM calls (default: `1`) |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | Ever Jobs Adzuna source (optional) |

Multiple LLM setups (Anthropic, Gemini, OpenRouter, Ollama, split providers per task) are documented inline in `.env.example`.

### Dashboard scoring & tiers

`data/user/{role}/input/scoring.yaml` (copied from `scoring.yaml.example`, gitignored like the CV) is the
single file that drives both the Target Companies tiering and the CV Gap Analysis ranking — edit it
to match your own priorities without touching code:

| Section | Controls |
|---|---|
| `preferred_industries`, `weights.*` | Points added/subtracted per job attribute (`jobfit/dashboards/scoring.py:score()`) |
| `tiers.dreamjob` / `tiers.easywin` | Placement thresholds (`jobfit/dashboards/scoring.py:tier()`) |
| `cv_match.*` | Stage weighting, similarity threshold, and title-exclusion regex for `/cv` |
| `tier_text.*` | Wording shown on each Target Companies tier card |

`preferred_industries` values must match, character-for-character, one of the canonical industry
names the classifier assigns to jobs — see `CANONICAL` in `jobfit/industry.py` for the full list.
A typo or a name not in that list doesn't error, it just never matches any job, so Dreamjob quietly
stays at 0 with no warning.

`tier_text` has one quirk worth knowing: each tier entry can define `summary` (the "Tier Overview"
one-liner), `criteria` ("Tier logic:" line), and `scoring_note` (the line under "Score formula") —
but whichever of those would restate a numeric threshold or on/off flag is generated in code instead,
so the displayed text can never drift out of sync when you tune a weight:
- `dreamjob` has no `summary` at all, only `tagline` (a short personal-voice phrase) — the rest of
  the sentence ("Startup in a preferred industry") is generated from `stages` (a list, e.g.
  `["startup"]` or `["startup", "mittelstand"]` — not everyone's dream job is a startup) /
  `require_preferred_industry`, and `criteria`/`scoring_note` are generated from `tiers.dreamjob.*`.
- `easywin` keeps `summary` (its wording doesn't name an exact number), but `criteria`/`scoring_note`
  are generated from `tiers.easywin.*`.
- `starred`, `cvbuilder`, `skip` have no numeric placement rule to derive text from (manual star /
  brand-DB lookup / catch-all), so all three fields are taken from the YAML verbatim.

See the comment block above `tier_text:` in `scoring.yaml.example` for the full field-per-tier breakdown.

## 🧪 Testing

```bash
uv sync --group tests
uv run pytest
```

Covers fetchers, enrichment, CV/Anschreiben pipelines, API smoke tests, and startup validation.

## 🔌 Extending

The core ships with a single role and a single market — everything below is how you (or future releases) grow coverage without rewriting the pipeline.

- **New role** → `jobfit/roles/{slug}.yaml` (skills/practices/title_re, see `devops.yaml`) + a one-line `jobfit/roles/{slug}.py` loader + register in `__init__.py` + `data/user/{slug}/input/CV_{slug}.md` + `data/user/{slug}/input/brands_prompt.txt` (see the `.example` files under `data/user/devops/input/` as a starting point)
- **New market / data source** → implement `run(args)` in `jobfit/fetchers/`, register in `fetchers/__init__.py`
- **New Softgarden company** → append to `data/jobs/softgarden_companies.csv`, then `jobfit fetch softgarden`

Examples throughout this README use `--role devops` — that's the only bundled role today. Swap the slug once your module is in place.

## 🎯 What This Project Demonstrates

- Designing and operating a multi-source data pipeline with idempotent ingestion
- Containerized deployment with health checks, migrations, and startup gates
- Database lifecycle management (Alembic, backups, SQLite → PostgreSQL migration)
- Building a dual-interface tool (CLI + REST API) from shared business logic
- Integrating LLMs into a production workflow with cost-aware manual steps
- Day-2 operations: sync schedules, zero-downtime cache rebuilds, incremental enrichment

---

*Portfolio project — a configurable job-search tool that doubles as a reference for data pipeline design, containerized ops, and full-stack Python development. Ships with one role and one market today; more coming, and you can add your own role module or fetcher module (see Extending).*
