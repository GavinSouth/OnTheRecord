# History — Phase 1 (context log)

Chronological log of every prompt/work item: what was asked, what was done, decisions, and what's next.
ROADMAP.md tracks feature completion; this file is the context a new session needs to pick up where we left off.

---

## 2026-10-23

### F1.1 — Scaffold carried over from ControlTower
- Asked: the repo started as a copy of ControlTower. Remove everything ControlTower-specific (features, history, backend code, app-specific libraries) and keep the general structure: the `.md` outlines, a Python backend, a web frontend, and an iOS app.
- Done:
  - **Removed:** the `controltower` package (models, API, timeline, stats, photos, demo), Alembic migrations + `alembic.ini`, all backend tests but the smoke test, `docs/HISTORY_P1–3.md`, `docs/mockups/`, the web app's pages/components/lib/api code, `web/openapi.json`.
  - **Dependencies:** backend runtime deps dropped (FastAPI, SQLAlchemy, Alembic, uvicorn, Pillow, pillow-heif, python-multipart) and dev `httpx2`; `uv.lock` regenerated. Web deps dropped: react-router, TanStack Query, openapi-fetch, openapi-typescript, @date-fns/tz, user-event; the `gen:api` script and the Vite `/api` proxy removed.
  - **Kept:** uv/ruff/mypy/pytest, pre-commit, CI (backend + web jobs), React/TS/Vite/Tailwind/oxlint/Vitest, `.claude/` allowlist and `/finish-feature` (de-branded; now also runs web checks).
  - **New:** `backend/src/ontherecord/` (package + `main()`), smoke test, placeholder `web/src/App.tsx` + test, `ios/README.md`, Xcode entries in `.gitignore`. CLAUDE.md, README, ROADMAP, ARCHITECTURE rewritten as outlines.
- Checks: backend (ruff, format, mypy, pytest: 2 passed) and web (oxlint, tsc, vitest: 1 passed, build) all green.
- Next: F1.2 product & data design: what OnTheRecord is, and the framework/database choices.

### Git history squashed
- Asked: squash the inherited ControlTower history into one initial commit.
- Done: `main` rebuilt as a single orphan commit with the same tree. Old history discarded locally (backup branch deleted at user request). The remote still has the old history until a force push.

### CI triggers trimmed
- User force-pushed the squashed `main` and deleted the remote `development` branch. CI now triggers on `main` only (`.github/workflows/ci.yml`).

### F1.2 — Product scope discussion (started)
- Asked: define scope and needs. User's answers:
  - **What:** a personal "one stop shop" for managing life. Three modules: **habits** (multiple habits, a daily check, kept history, shown as a GitHub-style contribution heatmap), **todos** (replaces Apple Reminders: nested folders/lists, checkable items, completion history kept in the database), **notes** (quick notes and comments through the day; later synced to an Obsidian vault where an agentic process files and tags them).
  - **Who:** the user only for now; possibly friends and the public later.
  - **Platforms:** ~95% iPhone. Web is for charts, analytics, data transparency, and richer views.
  - **Constraints:** sensitive data; aiming for a polished production app, not just a learning project, but learning along the way. v1 scope left to Claude's judgement.
- Done: purpose written into README and CLAUDE.md. Proposed the data model, stack (FastAPI + Postgres + SQLAlchemy 2 + Alembic), v1 scope, and phase order in chat. Waiting on user review of four open decisions: phase order (iOS before web), offline approach, encryption model, habit schedule semantics.

### F1.2 — Architecture written
- Asked: user approved all four (Backend → iOS → Web; online-only v1 with a sync-ready model; TLS + at-rest encryption, no E2E; unchecked scheduled day = miss, `skipped` protects streaks). Write ARCHITECTURE.md.
- Done:
  - `docs/ARCHITECTURE.md`: decisions D1–D15, Mermaid entity diagram (User, Habit, HabitCheck, TodoList (self-nesting), TodoItem, TodoEvent, Note), data rules (local-date checks, derived misses, soft-delete upsert on uncheck, float positions, append-only events), v1 API resource table, planned backend layout.
  - Key choices: FastAPI; PostgreSQL 18 (Docker locally, real Postgres in tests); SQLAlchemy 2 with sync sessions + Alembic + psycopg 3; UUID ids (client-supplied or server UUIDv7); `user_id` on every row; Sign in with Apple in F2.5 with a dev stub before; OpenAPI-generated Swift and TS clients; hosting chosen in F2.6.
  - ROADMAP restructured: Phase 2 backend (F2.1 foundation → F2.2 habits → F2.3 todos → F2.4 notes → F2.5 auth → F2.6 deploy), Phase 3 iOS, Phase 4 web, Phase 5 backlog (Obsidian + agent, offline, notifications, recurring, tags, sharing).
  - CLAUDE.md environment lines updated with the chosen stack.
- Next: F1.3 design system in Claude Design (needed before iOS/web screens). F2.1 can start independently.

### F1.2 — Product & data design complete
- Done: `docs/ARCHITECTURE.md` (D1–D15, entity diagram, v1 API), ROADMAP restructured (Phases 2–5), purpose + stack in README and CLAUDE.md. Checks green (backend: ruff, format, mypy, pytest 2 passed; web unchanged). Design system: no change (no UI work).
- Decisions: see the entry above. Short version: FastAPI + Postgres 18 + SQLAlchemy 2 (sync) + Alembic; `user_id` everywhere; sync-ready but online-only; local-date habit checks with derived misses; append-only todo events; Markdown notes; Sign in with Apple; OpenAPI-generated clients; Backend → iOS → Web.
- Next: F1.3 design system. Open questions for later features: host choice (F2.6); Apple Developer account needed by F2.5/F3.1.

### Explainer: habit checks as dates (D8)
- Asked: why habit checks use dates instead of timestamps. Explained in chat (no code change): a check answers a calendar-day question; timestamps need a timezone to map back to a day, which breaks with travel, late-night check-ins, and backfilling.

### Explainer: todo event log vs current state (D9)
- Asked: explain the append-only `todo_events` table vs storing only current state. Explained in chat (no code change): we use both. Rows hold the current state for fast reads; events hold the history for analytics, audit, undo, and the future agent and sync. Both are written in one transaction.

### F1.3 — Design system complete
- Asked: "No more explaining things right now. Let's do some developing." Picked up the next unchecked feature, F1.3. User chose the **calm native** direction (over ledger, bold/playful, or reusing ControlTower).
- Done: created the [OnTheRecord design system](https://claude.ai/artifact/Y9zVdSXCJazXweNe3JHdHi) (Claude Design, Design System type) with `tokens.json` (light + dark), a brand-book README (principles, voice, colour/type/space, iconography, how web and iOS consume it), components HabitRow, Heatmap, TodoRow (demo data, interactive previews), and a cover. Linked from `docs/ARCHITECTURE.md` › Design; ROADMAP ticked, Phase 1 marked done.
- Decisions: system fonts (SF Pro/SF Mono) so iOS gets Dynamic Type for free and the web needs no font downloads; one green `accent`; heatmap levels step in lightness (colour-blind safe); a missed day is `heat-0`, never red; `danger` only for destructive actions; type styles mirror iOS text styles; 4-pt spacing; flat surfaces with hairline separators, a shadow only for floating elements; six user-pickable habit colours. Streaks shown as text, no gamification icons. No logo yet (plain type).
- Design system: created (this feature).
- Next: F2.1 backend foundation (FastAPI, settings, Docker Postgres, SQLAlchemy + Alembic, User model, health, test DB fixtures, CI Postgres). Still open: web icon set (F4.1).
