FROM python:3.13-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
COPY api/pyproject.toml ./api/

RUN --mount=type=cache,id=uv-cache,target=/root/.cache/uv \
    UV_CONCURRENT_BUILDS=1 \
    UV_CONCURRENT_DOWNLOADS=2 \
    UV_CONCURRENT_INSTALLS=2 \
    uv sync --frozen --package api --no-dev --no-install-project 

COPY api/src ./api/src

WORKDIR /app/api

CMD ["uv", "run", "--project", "/app/api", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]

