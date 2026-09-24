# FROM python:3.13-slim
# WORKDIR /app/api
# COPY api/pyproject.toml api/uv.lock /app/api/
# RUN pip install --no-cache-dir uv && uv sync --project /app/api --no-dev
# COPY api/config /app/api/config
# COPY api/src /app/api/src
# COPY staging /app/staging
# CMD ["uv", "run", "--project", "/app/api", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.13-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

COPY api/pyproject.toml api/uv.lock ./

RUN --mount=type=cache,id=uv-cache,target=/root/.cache/uv \
    UV_CONCURRENT_BUILDS=1 \
    UV_CONCURRENT_DOWNLOADS=2 \
    UV_CONCURRENT_INSTALLS=2 \
    uv sync --frozen 

COPY api/src ./api/src

WORKDIR /app/api

CMD ["uv", "run", "--project", "/app/api", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]

