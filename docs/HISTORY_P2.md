# History — Phase 2 (context log)

Chronological log of every prompt/work item: what was asked, what was done, decisions, and what's next.
ROADMAP.md tracks feature completion; this file is the context a new session needs to pick up where we left off.

---

## 2026-10-23

### F2.1 — Backend foundation (started)
- Asked: "resume" → next unchecked feature, F2.1.
- Found: no container runtime on the Mac (no docker/brew/postgres). User chose **OrbStack** (Docker-compatible) to run the Compose Postgres locally.
- Done (code, unverified against a DB yet):
  - Deps: fastapi, uvicorn, pydantic-settings, sqlalchemy 2.1, alembic, psycopg[binary]; dev `httpx2` (Starlette's TestClient deprecates plain `httpx`).
  - `src/ontherecord/`: `main.py` (`create_app(settings)` factory + `run()` dev server, now the `ontherecord` script), `config.py` (`OTR_`-prefixed settings, `.env`), `db.py` (engine, session factory, `get_session`), `models/` (`Base` with naming convention, `UUIDPrimaryKey` = `uuidv7()` default, `Timestamps`, `User`), `schemas/` (`Health`, `UserRead`), `services/users.py` (race-safe dev user get-or-create), `api/` (`/api/v1/health` with 503 on DB down, `/api/v1/me`, `deps.py` with `SessionDep`/`CurrentUser`; stub returns 401 in prod).
  - Alembic: `alembic.ini`, `migrations/env.py` (URL from caller or `OTR_DATABASE_URL`), modern-typed template, ruff post-write hooks, `0001_create_users`.
  - `backend/compose.yaml` (postgres:18, localhost-only port, volume at `/var/lib/postgresql` as PG18 images expect), `backend/.env.example`. Root `.env.example` placeholder removed; stale `backend/data/` ignore removed.
  - Tests: `conftest.py` (creates `ontherecord_test` if missing, `downgrade base` + `upgrade head` once per run, SAVEPOINT session rolled back per test, `make_app` factory), health/me/config/migration-drift tests. Smoke test updated (package `main()` removed: it clashed with the `ontherecord.main` module).
  - CI: Postgres 18 service + `OTR_TEST_DATABASE_URL` on the backend job.
  - Docs: README setup/commands/layout, ARCHITECTURE backend layout + F2.1 conventions, CLAUDE.md commands, allowlist (alembic upgrade/current/history, docker compose up/ps/logs).
- Checks: ruff, format, mypy green; non-DB tests pass. DB tests waiting on OrbStack.

### F2.1 — DB tests green
- User installed OrbStack. Created `backend/.env` from the example with a random local password (git-ignored, not printed), `docker compose up -d` → Postgres 18 healthy.
- Full checks: ruff, format, mypy, pytest **11 passed** (re-run also green, so the `downgrade base` → `upgrade head` cycle works on an existing schema). Dev DB migrated to `0001 (head)`; server smoke test: `/api/v1/health` → ok, `/api/v1/me` → dev user with a v7 id.

### F2.1 — Backend foundation complete
- Done: FastAPI app factory, settings, local Postgres via Compose, SQLAlchemy 2 + Alembic, `User` + migration `0001`, `GET /api/v1/health`, `GET /api/v1/me` with the dev user stub, real-Postgres pytest fixtures, CI Postgres service. Files: `backend/src/ontherecord/**`, `backend/migrations/**`, `backend/alembic.ini`, `backend/compose.yaml`, `backend/.env.example`, `backend/tests/**`, `backend/pyproject.toml` + `uv.lock`, `.github/workflows/ci.yml`, README, ARCHITECTURE, CLAUDE.md, `.claude/settings.json`, `.gitignore`.
- Decisions: `OTR_` env prefix, `DATABASE_URL` required (no credential defaults in code); app factory with engine on `app.state` (no import-time globals); explicit commits in routes/services; constraint naming convention; ids default to `uuidv7()` in the DB; sequential Alembic revision ids (`0001`) with date-prefixed filenames; tests migrate a separate `_test` DB from scratch and roll back per test; a drift test compares models to the migrated schema; health returns 503 (not 500) on DB failure; dev stub is race-safe (`ON CONFLICT DO NOTHING`) and 401s in prod; Postgres bound to localhost only.
- Design system: no change (no UI work).
- Next: F2.2 Habits API (`Habit`, `HabitCheck`, CRUD, archive, idempotent check/uncheck, today view, streaks, heatmap).

### Explainer: what "Habits API" means
- Asked: what a Habits API is and what needs an API call. Explained in chat (no code change): the backend is the only holder of data (ARCHITECTURE overview); the iPhone and web apps read/write habits over HTTP endpoints. F2.2 builds those endpoints (create/edit/archive habits, check/uncheck a day, today view, stats, heatmap).
- Follow-up: confirmed the user's summary (app ↔ server ↔ DB) and refined it: request/response started by the app, JSON over HTTP, and the server validates and applies the rules rather than running whatever the app sends.
- Follow-up: clarified local topology: only Postgres runs in Docker (OrbStack's Linux VM, port published to 127.0.0.1:5432); the FastAPI server runs natively on the Mac via `uv run`. Both move to a cloud host in F2.6.
- Follow-up: clarified nothing is in the cloud yet: OrbStack, its VM, and the Postgres container all run on the Mac. Cloud = F2.6 (managed Postgres, not OrbStack).

### Explainer: running costs
- Asked: what the app will cost to run. Answered in chat from Oct 2026 pricing searches (third-party sources, to re-verify in F2.6): Apple Developer Program $99/yr (needed for TestFlight + Sign in with Apple); hosting for one user ≈ $5–15/mo (e.g. Railway Hobby $5/mo incl. $5 usage, Postgres billed as a service); Fly.io Managed Postgres starts at $38/mo, likely overkill at this scale; optional domain ~$10–15/yr; Phase 5 notes agent adds LLM API usage. Rough total ≈ $10–25/mo. Input for the F2.6 host decision.
- Follow-up: (1) one Apple Developer membership covers unlimited apps; free Apple ID can sideload to own phone but with 7-day re-signing and no TestFlight/Sign in with Apple. (2,3) the Mac + OrbStack *could* be the production server (self-hosting, ~$0, e.g. via Tailscale), but it must stay on, reachable off home Wi-Fi, and backed up by us. Cloud vs self-host is now an explicit F2.6 option.
- Follow-up: where hosting would likely be. Shortlist for F2.6: (A) Railway: API + Postgres 18 (template container) in one project, ~$5–10/mo; (B) Render: web service $7 + managed Postgres ~$6–7, PG18 unverified; (C) API on Railway/Fly + Neon serverless Postgres (free tier, managed backups), PG18 default unverified. Hard requirement surfaced: **Postgres 18** (migration 0001 uses native `uuidv7()`), plus automatic backups and encryption at rest (D13). Fallback if a host lacks PG18: generate UUIDv7 in Python instead.
- Follow-up: reusing Railway for multiple apps. Explained: Railway bills usage, not a fixed server, so one Hobby plan covers many projects (each app = its own service; costs add per use). One Postgres instance *can* hold several apps as separate databases + separate roles, but shares capacity, backups, upgrades and blast radius. Suggested: OnTheRecord (sensitive) gets its own Postgres service; small side projects can share another.

### Hosting & database plan written
- Asked: make notes and a plan for the hosting discussion, especially the separate-database structure inside Postgres; and whether the database is "mine" for data-engineering practice.
- Done: `docs/HOSTING.md`: dev vs prod, Railway plan + checklist (PG18, backups/tested restore, TLS, encryption at rest) and fallbacks, account layout (dedicated `ontherecord` project; later a `side-projects` project with one shared Postgres, one database + role per app), the inside of the OnTheRecord Postgres (`ontherecord` database with `public` + later `analytics` schemas, a `sandbox` database; roles `otr_owner` / `otr_app` / `otr_readonly` with the grant SQL), required code changes (split app/migration URLs, Compose role parity), data-practice tools and rules (read-only on prod, practise on a `pg_dump` copy), and an 8-step F2.6 plan. ROADMAP F2.6 expanded and two Phase 5 backlog items added (analytics/data practice, shared side-projects Postgres). ARCHITECTURE D15, README and CLAUDE.md link it.
- Answer: yes, it's a standard Postgres you own. Connect DBeaver/TablePlus/psql/pandas/DuckDB/dbt; locally today at localhost:5432 with the `backend/.env` credentials.
- Follow-up: user asked to see the role/database SQL; shared it from `docs/HOSTING.md` with line-by-line notes.
- HOSTING.md: `sandbox` is owned by a personal login (separate from the app roles). User: "resume development and come back to this when we get there" → F2.6. Docs committed separately.

### F2.2 — Habits API (started)
- Asked: resume development → F2.2 (backend only; no design canvas needed).
