# Hosting & database plan

Notes and plan for **F2.6 Deploy** (and beyond), from the Oct 2026 discussions logged in `docs/HISTORY_P2.md`. Nothing here is set up yet. Prices are from third-party sources as of 2026-10-23; re-check them before signing up.

## Dev vs production
| | Development (today) | Production (F2.6) |
|---|---|---|
| Where | Your Mac | A cloud host (plan: Railway) |
| API | `uv run ontherecord` (native, `127.0.0.1:8000`) | Deployed service, public HTTPS URL |
| Postgres | OrbStack container from `backend/compose.yaml` (`127.0.0.1:5432`) | A dedicated Postgres 18 service on the host |
| Data | Throwaway: break it freely | Real: what the iPhone uses daily |
| Connects via | `OTR_DATABASE_URL` in `backend/.env` | `OTR_DATABASE_URL` set as a host secret |

The code is identical in both. Only the environment variables differ.

## Host choice
**Plan: Railway** (Hobby, $5/mo including $5 of usage; billed by CPU, RAM, storage and egress). API and Postgres live in one project, and pushing to GitHub deploys.

Checks before committing to it (F2.6):
- [ ] **Postgres 18** available (migration `0001` uses native `uuidv7()`). Railway has PG18 templates; mount the volume at `/var/lib/postgresql` (the PG18 layout), never reuse a PG17 volume.
- [ ] **Automatic backups** on the Postgres volume, and a **restore actually tested**.
- [ ] Encryption at rest + TLS to the database (D13).
- [ ] Secrets only as host env vars.

Fallbacks:
- **API on Railway/Fly + Neon** (managed serverless Postgres, free tier, sleeps when idle).
- **Render** (~$7 web + ~$6–7 Postgres; PG18 unverified).
- **Self-host** on an always-on Mac via Tailscale (~$0, but you own uptime and backups).
- If a host lacks PG18, generate UUIDv7 ids in Python instead of with `uuidv7()`.

Not chosen: Fly.io Managed Postgres ($38+/mo, overkill for one user).

**Expected cost:** ~$5–10/mo hosting + Apple Developer $99/yr ≈ **$10–20/mo**. An optional domain is ~$10–15/yr.

## Railway layout (multiple apps)
One Railway account (one Hobby plan) holds many **projects**; each app is a project. Usage adds up across all of them.

```
Railway account (Hobby plan)
├── project: ontherecord             ← sensitive, daily use: nothing else shares it
│   ├── service: api                 FastAPI, deployed from backend/
│   └── service: postgres            Postgres 18, dedicated to OnTheRecord
│
└── project: side-projects           ← later, for small/low-stakes apps
    ├── service: <app>-api           one service per app's API
    └── service: postgres-shared     one Postgres, one database + one role per app
```

**Why OnTheRecord gets its own Postgres:** a shared server means shared fate (one crash or restart stops every app), shared backups (restoring one app is fiddly), shared upgrades (all apps move to PG19 at once) and shared risk (one leaked login is a door to everything). An idle small Postgres costs a few dollars a month in usage, which is cheap insurance for sensitive data.

**Rules for the shared Postgres:** one database per app, one login role per app, `CONNECT` revoked from everyone else. Apps never share tables.

## Inside the OnTheRecord Postgres
A Postgres **server** (instance) holds **databases**. Each database holds **schemas** (namespaces), and schemas hold **tables**. Logins are **roles**, and permissions are granted to roles.

```
Postgres 18 server (Railway service "postgres")
├── database: ontherecord            the app's real data
│   ├── schema: public               app tables (users, habits, …); Alembic owns these
│   └── schema: analytics            (later) your views/derived tables for practice and the web app
├── database: sandbox                your data-engineering playground: write anything here
└── roles (logins)
    ├── postgres       superuser from Railway: admin only, never used by the app
    ├── otr_owner      owns `ontherecord` + its tables; used only by migrations
    ├── otr_app        the API: read/write rows, no CREATE/DROP/ALTER
    └── otr_readonly   you + external tools: SELECT only, forced read-only
```

Why three app-side roles (least privilege):
- **`otr_app`** can't drop or alter tables, so a bug or SQL injection in the API can't destroy the schema.
- **`otr_owner`** is used only by `alembic upgrade head` during a deploy.
- **`otr_readonly`** lets DBeaver, Python notebooks and so on browse real data with zero chance of changing it.

Role setup (run once as `postgres` in F2.6; passwords generated, stored only in Railway variables and your password manager):

```sql
CREATE ROLE otr_owner    LOGIN PASSWORD '<generated>';
CREATE ROLE otr_app      LOGIN PASSWORD '<generated>';
CREATE ROLE otr_readonly LOGIN PASSWORD '<generated>';
ALTER ROLE otr_readonly SET default_transaction_read_only = on;

CREATE DATABASE ontherecord OWNER otr_owner;
REVOKE ALL ON DATABASE ontherecord FROM PUBLIC;
GRANT CONNECT ON DATABASE ontherecord TO otr_app, otr_readonly;

\c ontherecord
-- PG15+: the public schema belongs to the database owner (otr_owner).
GRANT USAGE ON SCHEMA public TO otr_app, otr_readonly;
-- Tables otr_owner creates in future migrations get these grants automatically.
ALTER DEFAULT PRIVILEGES FOR ROLE otr_owner IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO otr_app;
ALTER DEFAULT PRIVILEGES FOR ROLE otr_owner IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO otr_app;
ALTER DEFAULT PRIVILEGES FOR ROLE otr_owner IN SCHEMA public
    GRANT SELECT ON TABLES TO otr_readonly;

CREATE ROLE <your-name> LOGIN PASSWORD '<generated>';   -- personal login for experiments, separate from app roles
CREATE DATABASE sandbox OWNER <your-name>;                 -- free-for-all playground
```

Code changes this needs (F2.6):
- **Two URLs:** `OTR_DATABASE_URL` (as `otr_app`) for the API, and `OTR_MIGRATIONS_DATABASE_URL` (as `otr_owner`) read by `migrations/env.py`, falling back to the first.
- **Deploy step:** `alembic upgrade head` with the owner URL, then start the API.
- **Local parity:** a Compose init script creating the same roles, so permission bugs show up on the Mac first.

## Your data: data-engineering practice
Yes, it's a normal Postgres you fully own. Anything that speaks Postgres can connect:
- **GUI clients:** DBeaver (free), TablePlus, Postico (Mac), DataGrip, pgAdmin.
- **CLI:** `psql`.
- **Code:** Python with SQLAlchemy/psycopg, pandas or polars (`read_sql`), DuckDB (its `postgres` extension can query Postgres tables directly), dbt for modelled transformations, notebooks.
- **Pipelines:** export to CSV/Parquet, load into DuckDB or a warehouse, schedule jobs.

**Today, locally:** connect any client to `localhost:5432` with the user, password and database from `backend/.env` (`ontherecord`, or `ontherecord_test`, which the tests wipe). This is the safest place to practise.

**Rules once production exists:**
1. **Never practise writes on production.** Browse prod only as `otr_readonly`.
2. **Practise on a copy:** `pg_dump` production → `pg_restore` into the local OrbStack Postgres (or into `sandbox`), then reshape, query and break it freely.
3. **Derived stuff goes in `analytics`** (views, rollups like daily habit completion). A migration-managed `analytics` schema can later feed the web dashboards (Phase 4).
4. **Connect over TLS** with a strong password. Prefer Railway's private networking or a temporary public TCP proxy over leaving the database permanently exposed.
5. **Remember it's sensitive:** exports and notebooks with real data stay on your machine, out of git and out of public services.

## Plan
**F2.6 Deploy** (ROADMAP):
1. Verify the Railway checklist above (PG18, backups + restore test, TLS, encryption at rest). If it fails → fallback.
2. Create the `ontherecord` project: Postgres 18 service (volume at `/var/lib/postgresql`) + API service from `backend/`.
3. Run the role/database SQL above. Store the passwords in Railway variables + your password manager.
4. Code: split app vs migration URLs; deploy runs migrations as `otr_owner`; Compose init script for local role parity.
5. Secrets: `OTR_ENV=prod`, `OTR_DATABASE_URL`, `OTR_MIGRATIONS_DATABASE_URL` `OTR_JWT_SECRET` (a fresh one, never the dev value), `OTR_APPLE_CLIENT_IDS` (the iOS bundle id, from F3.1). The app refuses to start in prod without the last two.
6. HTTPS URL for the iOS app; `GET /api/v1/health` as the host's health check.
7. Backups: confirm the schedule, do one test restore into `sandbox`, and write the restore steps into this file.
8. Data access: connect DBeaver (or similar) as `otr_readonly`; write a `pg_dump` → local restore script (`backend/scripts/`).

**Later (Phase 5 backlog):** an `analytics` schema with derived tables/views, a scheduled export or dbt project for practice, and a `side-projects` Railway project with a shared Postgres for small apps.
