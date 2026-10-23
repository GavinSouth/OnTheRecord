# OnTheRecord

A personal life-management app: a **habit tracker** with a GitHub-style heatmap, a **todo** list with nested lists and history, and **notes** for quick capture (later synced to Obsidian). iPhone-first, with a web app for charts and analytics.

**Status:** Phase 1 done (scaffold, product & data design, design system). Phase 2 in progress: F2.1 backend foundation: a FastAPI app with settings, local Postgres in Docker, SQLAlchemy + Alembic, a `users` table, `GET /api/v1/health`, `GET /api/v1/me` (dev-only user stub), and tests against real Postgres (locally and in CI). Next: F2.2 habits API. See [ROADMAP.md](ROADMAP.md) and [docs/](docs/).

## Architecture
- **Backend** (`backend/`): Python 3.13, FastAPI, PostgreSQL 18, SQLAlchemy 2 + Alembic. The single source of data; REST API under `/api/v1`.
- **iOS** (`ios/`): SwiftUI, the primary client for daily use. Built before web.
- **Web app** (`web/`): React + TypeScript + Vite + Tailwind, for analytics (heatmaps, trends, history).
- Both clients are generated from the backend's OpenAPI spec. Auth: Sign in with Apple.

Decisions, data model, and API: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Hosting, database roles, and how to query your own data: [docs/HOSTING.md](docs/HOSTING.md). Look and components: the [OnTheRecord design system](https://claude.ai/artifact/Y9zVdSXCJazXweNe3JHdHi) (calm, iOS-native; light and dark).

## Tech stack
| Concern | Tool |
|---|---|
| Python + dependencies | [uv](https://docs.astral.sh/uv/) (`backend/uv.lock`) |
| API / database (from F2.1) | FastAPI, PostgreSQL 18, SQLAlchemy 2, Alembic, psycopg 3 |
| Lint + format | ruff |
| Type checking | mypy (strict) |
| Tests | pytest |
| Git hooks | pre-commit |
| CI | GitHub Actions (`.github/workflows/ci.yml`) |
| Web app | Node 24, React 19, TypeScript 6, Vite 8, Tailwind 4 |
| Web lint / tests | oxlint, tsc, Vitest + Testing Library |
| iOS | Swift / SwiftUI (not started) |

## Setup
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # install uv (once)
# Docker runtime for local Postgres: OrbStack (https://orbstack.dev) or Docker Desktop

cd backend
uv sync                      # creates .venv with Python 3.13 + deps
uv run pre-commit install    # enable git hooks (once)
cp .env.example .env         # local settings; change the password (never commit .env)
docker compose up -d         # Postgres 18 on localhost:5432 (data kept in a Docker volume)
uv run alembic upgrade head  # create/upgrade the schema
uv run ontherecord           # API on http://127.0.0.1:8000 (docs at /docs), auto-reload

cd ../web
npm install                  # Node 24 (web/.nvmrc)
npm run dev                  # http://localhost:5173
```

## Commands (from `backend/`)
```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest   # all checks
uv run ruff check --fix . && uv run ruff format .                                          # auto-fix
uv run alembic revision --autogenerate -m "<what>"   # new migration from model changes (review it)
uv run alembic upgrade head                          # apply migrations
docker compose up -d / docker compose down           # start / stop Postgres (add -v to wipe data)
```
Tests need Postgres running: they create `ontherecord_test` on the same server, migrate it from scratch once per run, and roll each test back.

## Commands (from `web/`)
```bash
npm run lint && npm run typecheck && npm test && npm run build   # all checks
```

## Project layout
```
backend/            Python package, tests, Alembic, compose.yaml (local Postgres), .env.example
  src/ontherecord/  main.py (app factory), config.py, db.py, models/, schemas/, services/, api/
  migrations/       Alembic migrations (versions/0001_… sequential ids)
web/                React app (src/)
ios/                SwiftUI app (placeholder)
docs/               ARCHITECTURE.md (decisions), HOSTING.md (deploy + database plan), HISTORY_P<phase>.md (context log per phase), python_research.md (tooling notes)
.github/workflows/  CI
.claude/            Claude Code settings + /finish-feature skill
.gitignore          secrets (.env), venvs, caches, Xcode, OS/editor files
```
