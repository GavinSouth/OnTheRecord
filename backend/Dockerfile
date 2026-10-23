# Production image for the API (F2.6). From backend/: `docker build -t ontherecord-api .`
# Host-agnostic: Railway builds it (railway.json), and so could Render or Fly.

FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /bin/uv
# Compile .pyc once at build time; copy (not hardlink) out of uv's cache; use the image's Python.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app
# Dependencies first, so this layer is reused until the lockfile changes.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
# Non-editable: the package is installed into the venv, so src/ isn't needed at runtime.
RUN uv sync --locked --no-dev --no-editable

FROM python:3.13-slim
RUN useradd --system --uid 1001 app
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY alembic.ini ./
COPY migrations ./migrations
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER app
# The host sets PORT. Migrations run separately, before the new version goes live
# (railway.json preDeployCommand: `alembic upgrade head`, as otr_owner).
CMD ["sh", "-c", "exec uvicorn --factory ontherecord.main:create_app --host 0.0.0.0 --port ${PORT:-8000}"]
