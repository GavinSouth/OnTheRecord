# Architecture

OnTheRecord's design decisions. Set by ROADMAP F1.2 (product & data design) and kept current as features land.

## Overview
A personal life-management app with three modules:
- **Habits**: a daily check per habit, streaks, and a GitHub-style contribution heatmap.
- **Todos**: nested lists of checkable items. Replaces Apple Reminders and keeps the full completion history.
- **Notes**: quick Markdown capture through the day. Later synced to an Obsidian vault, where an agent files and tags notes.

One backend, two clients:
- **Backend** (`backend/`): Python 3.13, FastAPI, PostgreSQL. The only holder of data.
- **iOS** (`ios/`): SwiftUI. The primary client (~95% of use): quick checks, todos, capture.
- **Web** (`web/`): React + TypeScript. Analytics, charts, history, and richer views.

Single user (the owner) for now, built so it can open to friends or the public later.

## Decisions at a glance
| # | Decision | Why |
|---|---|---|
| D1 | **v1 = habits, todos, notes**, online, one user | The smallest version the owner will use daily. Everything else goes to the Phase 5 backlog. |
| D2 | **Every row carries `user_id`** from day one, and every query is scoped by it | Multi-user later costs nothing now. Retrofitting tenancy onto live data is a painful migration. |
| D3 | **FastAPI** for HTTP | Pydantic types fit mypy strict. It generates an OpenAPI spec automatically, which drives both clients (D12). |
| D4 | **PostgreSQL 18** | Multi-user, the production standard, and strong date functions for streaks and heatmaps. Native `uuidv7()`. Offered as a managed service by every host. Local dev runs Postgres in Docker. Tests run against real Postgres, not SQLite. |
| D5 | **SQLAlchemy 2.0 (typed, sync sessions) + Alembic**, driver **psycopg 3** | The standard Python ORM and migration pair. Sync sessions are simpler than async. FastAPI runs sync endpoints in a thread pool, which is plenty at this scale. |
| D6 | **UUID primary keys.** Clients may supply an id; otherwise the server generates UUIDv7 | Clients can create records before the server replies, which enables optimistic UI now and offline sync later. v7 ids sort by creation time, which keeps indexes efficient. |
| D7 | **Sync-ready, but online-only in v1**: `created_at`, `updated_at`, `deleted_at` (soft delete) on every mutable table | Full offline sync is a hard problem and is deferred. These columns are all it will need, so adding it later won't require a redesign. |
| D8 | **Habit checks are local calendar dates.** "Missed" is derived, not stored. A `skipped` status protects streaks | A check answers "did I do it that day?" in the owner's local day, so it can't drift across timezones. A miss = a scheduled day with no check. |
| D9 | **Todo history = append-only `todo_events`**, written in the same transaction as the item change | Apple Reminders keeps only the current state. An event log keeps everything and feeds web analytics and the future Obsidian agent. |
| D10 | **Notes stored as Markdown** | Maps 1:1 to Obsidian files later. |
| D11 | **Auth: Sign in with Apple**, then server-issued access and refresh tokens (details in F2.5) | iPhone-first, and it works on web too. Until F2.5, a dev-only stub dependency supplies the current user. |
| D12 | **The OpenAPI spec is the API contract.** Clients are generated from it: Swift (`swift-openapi-generator`) and TypeScript (`openapi-typescript` + `openapi-fetch`) | One source of truth. A backend change that breaks a client fails type-checking, not at runtime. |
| D13 | **Security: TLS in transit + the host's encryption at rest. No end-to-end encryption.** Secrets only in env vars | With E2E, the server couldn't read the data, which would rule out server-side analytics and the notes agent. Can be revisited for specific fields later. |
| D14 | **Phase order: Backend → iOS → Web** | The phone is the daily driver. The API is still designed for web analytics from the start (aggregate endpoints, D9 events). |
| D15 | **Hosting: decided in F2.6**, before the first deploy (likely Fly.io or Railway + managed Postgres) | The phone needs a reachable server. No reason to lock in a host before there is something to deploy. |

## Data model

```mermaid
erDiagram
    USER ||--o{ HABIT : owns
    USER ||--o{ TODO_LIST : owns
    USER ||--o{ NOTE : writes
    HABIT ||--o{ HABIT_CHECK : "checked on"
    TODO_LIST ||--o{ TODO_LIST : "contains (nesting)"
    TODO_LIST ||--o{ TODO_ITEM : holds
    TODO_ITEM ||--o{ TODO_EVENT : "history"

    USER {
        uuid id PK
        text apple_sub UK "Sign in with Apple subject"
        text email "nullable"
        text display_name
        text timezone "IANA, e.g. America/Chicago"
        timestamptz created_at
        timestamptz updated_at
    }
    HABIT {
        uuid id PK
        uuid user_id FK
        text name
        text description "nullable"
        text color
        smallint_array schedule_days "ISO weekdays 1-7; all 7 = daily"
        date started_on "misses only count from here"
        float position
        timestamptz archived_at "nullable; history kept"
        timestamptz deleted_at "nullable"
    }
    HABIT_CHECK {
        uuid id PK
        uuid user_id FK
        uuid habit_id FK
        date date "local day; unique with habit_id"
        enum status "done | skipped"
        timestamptz deleted_at "nullable; uncheck"
    }
    TODO_LIST {
        uuid id PK
        uuid user_id FK
        uuid parent_id FK "nullable; null = top level"
        text name
        float position
        timestamptz deleted_at "nullable"
    }
    TODO_ITEM {
        uuid id PK
        uuid user_id FK
        uuid list_id FK
        text title
        text notes "nullable, Markdown"
        date due_date "nullable"
        float position
        timestamptz completed_at "nullable"
        timestamptz deleted_at "nullable"
    }
    TODO_EVENT {
        uuid id PK
        uuid user_id FK
        uuid item_id FK
        enum type "created | edited | completed | reopened | moved | deleted | restored"
        jsonb data "e.g. changed fields, from/to list"
        timestamptz occurred_at
    }
    NOTE {
        uuid id PK
        uuid user_id FK
        text body "Markdown"
        timestamptz deleted_at "nullable"
    }
```

`created_at` and `updated_at` exist on every table but are left out of the diagram for brevity.

Rules:
- **All timestamps are `timestamptz`, stored in UTC.** Habit check dates are plain `date` values in the owner's local day (D8). `user.timezone` lets the server know what "today" means for streaks.
- **Missed day** = a date on or after `started_on`, whose weekday is in `schedule_days`, with no live check. In v1, editing a schedule re-evaluates past days. Versioned schedules can come later if that ever matters.
- **Uncheck** soft-deletes the check. Re-checking the same day upserts on `(habit_id, date)` and clears `deleted_at`.
- **Ordering** uses a float `position`. To insert between two rows, use the midpoint of their positions. Renumber the rows if the gaps get too small.
- **Nesting**: a list can contain lists and items, so lists also act as folders. The service layer rejects moves that would create a cycle. Deleting a list soft-deletes its subtree.
- **Todo events** are only ever inserted, never updated or deleted. Every item mutation goes through a service function that writes the event in the same transaction.

## API
REST + JSON under `/api/v1`. The spec is generated by FastAPI at `/openapi.json` (D12). Lists that grow (notes, events) use cursor pagination.

| Area | Endpoints |
|---|---|
| Health | `GET /health` |
| Auth (F2.5) | `POST /auth/apple` (Apple identity token → access + refresh), `POST /auth/refresh`, `POST /auth/logout`, `GET /me`, `PATCH /me` |
| Habits | `GET /habits?for_date=YYYY-MM-DD&include_archived=` (adds that day's check status: the iOS "today" view), `POST /habits`, `GET/PATCH/DELETE /habits/{id}` (archive = `PATCH archived: true`) |
| Habit checks | `PUT /habits/{id}/checks/{date}` (body: `status`; idempotent), `DELETE /habits/{id}/checks/{date}`, `GET /habits/{id}/checks?from=&to=` |
| Habit analytics | `GET /habits/{id}/stats` (current/longest streak, completion rate), `GET /habits/heatmap?from=&to=&habit_id=` (per day: scheduled, done, skipped) |
| Todo lists | `GET /lists` (flat, with `parent_id`; the client builds the tree), `POST /lists`, `PATCH /lists/{id}` (rename, move, reorder), `DELETE /lists/{id}` |
| Todo items | `GET /lists/{id}/items?completed=`, `POST /lists/{id}/items`, `PATCH /items/{id}` (edit, move, reorder, `completed: true/false`), `DELETE /items/{id}` |
| Todo history | `GET /items/{id}/events`, `GET /todo-events?from=&to=` (analytics) |
| Notes | `GET /notes?q=&cursor=` (newest first, full-text search), `POST /notes`, `GET/PATCH/DELETE /notes/{id}` |

## Backend layout (F2.1)
```
backend/
  compose.yaml          local Postgres 18 (Docker); values from backend/.env
  .env.example          OTR_* settings + POSTGRES_* for compose
  alembic.ini, migrations/   Alembic; sequential revision ids (0001, 0002, …)
  src/ontherecord/
    main.py             create_app(settings) factory; `run()` = dev server
    config.py           Settings (pydantic-settings, OTR_ env prefix)
    db.py               engine, session factory, get_session dependency
    models/             SQLAlchemy models; base.py = Base, UUIDPrimaryKey, Timestamps
    schemas/            Pydantic request/response models
    services/           business rules (routes call these)
    api/                routers under /api/v1; deps.py = SessionDep, CurrentUser
  tests/                conftest.py: real Postgres, migrated once, rollback per test
```
Conventions set in F2.1:
- **App factory**: `create_app(settings)` builds the engine and stores it on `app.state`, so tests can build an app against any database without global state.
- **Sessions**: one per request (`SessionDep`). Routes/services call `session.commit()` explicitly; anything uncommitted rolls back on close.
- **Constraint names** follow a naming convention (`pk_users`, `uq_users_apple_sub`, `fk_<table>_<col>_<ref>`) so later migrations can alter them reliably.
- **Ids** default to `uuidv7()` in the database (D6), so rows inserted by any path get one.
- **Dev auth stub**: `CurrentUser` resolves to a single local user (`apple_sub = "dev-local"`) in `dev`/`test`, and returns 401 in `prod`. Replaced in F2.5.
- **Tests**: the session-scoped fixture runs `alembic downgrade base` + `upgrade head`, so every migration's up and down path runs on every test run. Each test uses a SAVEPOINT-joined session in an outer transaction that is rolled back.

## Later (not in v1)
Obsidian sync and the notes agent, offline sync, reminders and notifications, recurring todos, tags, numeric and "N× per week" habits, sharing, public sign-up. See ROADMAP Phase 5.

## Design
- **Design system:** [OnTheRecord](https://claude.ai/artifact/Y9zVdSXCJazXweNe3JHdHi) (Claude Design, F1.3). The truth for look and components. Direction: **calm native**. iOS-feeling, system fonts (SF Pro / SF Mono), warm-grey neutrals, one green `accent`, and the habit heatmap as the signature element. Light and dark.
  - Tokens: colour (ground, ink, accent, `heat-0`…`heat-4` + `heat-skip`, `warning`, `danger`, six `habit-*` colours), type styles mirroring iOS text styles, 4-pt spacing, radii by role, `shadow-float`, sizes (44 tap target, 28 check, 12 heatmap cell).
  - Components: HabitRow, Heatmap, TodoRow (+ cover).
  - Rules worth remembering: a missed day is never red; `danger` is only for destructive actions; habit colours never carry meaning without the name.
  - Using it: web maps tokens to CSS variables + Tailwind `@theme` (F4.1); iOS maps colours to asset-catalog Color Sets and type to `Font.TextStyle` (F3.1).
- Canvases: none yet. The first screens (iOS Today, todos, notes) are designed in F3.1.
