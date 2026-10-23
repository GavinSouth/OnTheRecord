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
