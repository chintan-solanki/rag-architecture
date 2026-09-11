FROM python:3.13-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

COPY ingestion/pyproject.toml ingestion/uv.lock ./

ENV NLTK_DATA=/app/nltk_data

RUN mkdir -p "$NLTK_DATA" && \
    uv run python -c "import nltk; nltk.download('punkt', download_dir='$NLTK_DATA')"

RUN --mount=type=cache,id=uv-cache,target=/root/.cache/uv \
    UV_CONCURRENT_BUILDS=1 \
    UV_CONCURRENT_DOWNLOADS=2 \
    UV_CONCURRENT_INSTALLS=2 \
    uv sync --frozen 

COPY ingestion/src ./ingestion/src