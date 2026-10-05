FROM python:3.13-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_HEADLESS=true

COPY pyproject.toml uv.lock ./
COPY ui/pyproject.toml ./ui/

RUN --mount=type=cache,id=uv-cache,target=/root/.cache/uv \
    UV_CONCURRENT_BUILDS=1 \
    UV_CONCURRENT_DOWNLOADS=2 \
    UV_CONCURRENT_INSTALLS=2 \
    uv sync --frozen --package ui --no-dev --no-install-project

COPY ui/ ./ui/

EXPOSE 8501

CMD ["uv", "run", "--project", "/app/ui", "streamlit", "run", "/app/ui/app.py"]
