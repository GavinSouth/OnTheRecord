# Roadmap

OnTheRecord: a personal life-management app with **habits** (daily checks + heatmap), **todos** (nested lists + history), and **notes** (quick capture, later Obsidian). Three clients of one system: a **Python backend** (HTTP API + data), an **iOS app** (daily use), and a **web app** (analytics). Decisions: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Phase 1 — Foundation & Design  [IN PROGRESS]
- [x] F1.1 Scaffold: uv + Python 3.13 package in `backend/`, ruff/mypy/pytest, pre-commit, GitHub Actions CI, React + TypeScript + Vite + Tailwind shell in `web/`, `ios/` placeholder, Claude allowlist + `/finish-feature` skill. (Carried over from a previous project and stripped to the structure.)
- [x] F1.2 Product & data design. Scope (habits, todos, notes; v1 online, single user), entities and relationships, stack (FastAPI + PostgreSQL 18 + SQLAlchemy 2 + Alembic), auth direction (Sign in with Apple), phase order (backend → iOS → web). Output: `docs/ARCHITECTURE.md` (decisions D1–D15, entity diagram, v1 API resource list).
- [ ] F1.3 Design system: create the OnTheRecord design system in Claude Design and link it from `docs/ARCHITECTURE.md`.

## Phase 2 — Backend Core  [NOT STARTED]
- [ ] F2.1 Backend foundation: FastAPI app factory, settings (pydantic-settings), local Postgres (Docker Compose), SQLAlchemy 2 + Alembic, `User` model + first migration, `GET /health`, dev-only current-user stub, pytest fixtures against a real test database, CI Postgres service.
- [ ] F2.2 Habits API: `Habit` + `HabitCheck` models, CRUD, archive, idempotent check/uncheck by date, `for_date` today view, streak/completion stats, heatmap aggregate.
- [ ] F2.3 Todos API: nested `TodoList` (cycle-safe moves, subtree soft delete), `TodoItem` (complete/reopen, move, reorder), append-only `TodoEvent` log, history endpoints.
- [ ] F2.4 Notes API: `Note` CRUD, newest-first cursor pagination, Postgres full-text search.
- [ ] F2.5 Auth: Sign in with Apple token verification, server-issued access + refresh tokens, replace the dev stub, user-scoping tests (one user can never see another's rows).
- [ ] F2.6 Deploy: choose host + managed Postgres, secrets, migrations on deploy, HTTPS, backups.

## Phase 3 — iOS  [NOT STARTED]
- [ ] F3.1 iOS project: Xcode app in `ios/`, client generated from OpenAPI (`swift-openapi-generator`), Sign in with Apple, app shell + navigation (design canvas first).
- [ ] F3.2 Habits: today view with one-tap check/skip, habit create/edit/archive, streaks, a compact heatmap.
- [ ] F3.3 Todos: nested lists, items, complete/reorder/move, completed history.
- [ ] F3.4 Notes: fast capture, list, search, edit.
- [ ] F3.5 TestFlight build on the owner's iPhone.

## Phase 4 — Web  [NOT STARTED]
- [ ] F4.1 Web shell: router, generated TS client (`openapi-typescript` + `openapi-fetch`), Sign in with Apple, layout (design canvas first).
- [ ] F4.2 Habit analytics: full-year contribution heatmap per habit and combined, streaks, completion trends.
- [ ] F4.3 Todo history + notes views: completion analytics from the event log, notes browser and search.

## Phase 5 — Later  [BACKLOG, unordered]
- Obsidian vault sync for notes; an agentic process that files and tags notes.
- Offline mode + sync on iOS (uses the D6/D7 data model).
- Reminders and push notifications (habits, due todos).
- Recurring todos; tags; numeric and "N× per week" habits.
- Sharing and public sign-up.
