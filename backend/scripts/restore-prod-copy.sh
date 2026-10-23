#!/usr/bin/env bash
# Copy production into the local Postgres, to practise on (docs/HOSTING.md, rule 2).
#
#   OTR_SOURCE_DATABASE_URL='postgresql://otr_readonly:…@host:port/ontherecord?sslmode=require' \
#       scripts/restore-prod-copy.sh [target_db]      # from backend/
#
# Streams pg_dump | pg_restore inside the local Postgres 18 container, so the client
# tools match the server version and no dump file of real data lands on disk.
# The target (default `ontherecord_prodcopy`) is dropped and recreated each time.
set -euo pipefail
cd "$(dirname "$0")/.."

source_url="${OTR_SOURCE_DATABASE_URL:?set OTR_SOURCE_DATABASE_URL (connect as otr_readonly)}"
target="${1:-ontherecord_prodcopy}"
if [[ "$target" != *copy* ]]; then
    echo "refusing: target '$target' must contain 'copy' (never the dev or test database)" >&2
    exit 1
fi

# pg_dump speaks libpq URLs, not SQLAlchemy's `postgresql+psycopg://`. Passed as an env
# var name only (-e NAME), so the URL never shows up in `ps` output.
export OTR_SOURCE_DATABASE_URL="${source_url/+psycopg/}" OTR_TARGET="$target"
docker compose exec -T -e OTR_SOURCE_DATABASE_URL -e OTR_TARGET db sh -euc '
    dropdb --if-exists --force -U "$POSTGRES_USER" "$OTR_TARGET"
    createdb -U "$POSTGRES_USER" "$OTR_TARGET"
    pg_dump --format=custom --no-owner --no-privileges "$OTR_SOURCE_DATABASE_URL" \
        | pg_restore --exit-on-error --no-owner --no-privileges -U "$POSTGRES_USER" -d "$OTR_TARGET"
'
echo "Restored into '$target' on the local Postgres (owned by your local superuser)."
