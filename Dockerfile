FROM node:24-bookworm-slim@sha256:a5f4366e834695d5f363b920c104953a535d3a9864d1bdf74566a0ebe01daee5 AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/index.html frontend/auth.html frontend/tsconfig.json frontend/vite.config.ts ./
COPY frontend/src ./src
COPY integrations/personalization/client.ts /integrations/personalization/client.ts
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.11.29@sha256:eb2843a1e56fd9e30c7276ce1a52cba86e64c7b385f5e3279a0e08e02dd058fc AS uv
FROM python:3.13-slim-bookworm@sha256:a1165e272e578941b84abc79e4ab38a0305cd12803a5c4247979ac7655f4d641 AS backend
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
COPY backend/counterpress ./backend/counterpress
RUN uv sync --locked --no-dev --no-editable --python /usr/local/bin/python --no-cache
ENV TIKTOKEN_CACHE_DIR=/app/tokenizer-cache
RUN .venv/bin/python -c "import tiktoken; tiktoken.get_encoding('o200k_base')"

FROM python:3.13-slim-bookworm@sha256:a1165e272e578941b84abc79e4ab38a0305cd12803a5c4247979ac7655f4d641 AS runtime
WORKDIR /app
RUN groupadd --gid 10001 counterpress && useradd --uid 10001 --gid 10001 --no-create-home counterpress \
    && mkdir /data && chown 10001:10001 /data
COPY --from=backend /app/.venv /app/.venv
COPY --from=backend /app/tokenizer-cache /app/tokenizer-cache
COPY --from=frontend /build/dist /app/static
COPY fixtures /app/fixtures
ENV PATH="/app/.venv/bin:$PATH" \
    TIKTOKEN_CACHE_DIR=/app/tokenizer-cache \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    COUNTERPRESS_DB_PATH=/data/counterpress.sqlite3 \
    COUNTERPRESS_FIXTURE_DIR=/app/fixtures COUNTERPRESS_STATIC_DIR=/app/static
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=4).close()"]
CMD ["uvicorn", "counterpress.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
