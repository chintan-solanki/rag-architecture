# FROM python:3.13-slim

# WORKDIR /app

# COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# ENV PATH="/app/.venv/bin:$PATH"
# ENV PYTHONUNBUFFERED=1

# COPY ingestion/pyproject.toml ingestion/uv.lock ./

# ENV NLTK_DATA=/app/nltk_data

# RUN mkdir -p "$NLTK_DATA" && \
#     uv run python -c "import nltk; nltk.download('punkt', download_dir='$NLTK_DATA')"

# RUN --mount=type=cache,id=uv-cache,target=/root/.cache/uv \
#     UV_CONCURRENT_BUILDS=1 \
#     UV_CONCURRENT_DOWNLOADS=2 \
#     UV_CONCURRENT_INSTALLS=2 \
#     uv sync --frozen 

# COPY ingestion/src ./ingestion/src

FROM python:3.13-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

ENV NLTK_DATA=/app/.nltk_data

COPY .nltk/.nltk_data /app/.nltk_data

COPY pyproject.toml uv.lock ./
COPY ingestion/pyproject.toml ./ingestion/
COPY common/pyproject.toml ./common/

# Download and cache external dependencies (like PyMuPDF)
# --no-install-workspace prevents uv from looking for the actual code files yet, which are copied later.
RUN --mount=type=cache,id=ingestion-uv-cache,target=/root/.cache/uv \
    UV_CONCURRENT_BUILDS=1 \
    UV_CONCURRENT_DOWNLOADS=2 \
    UV_CONCURRENT_INSTALLS=2 \
    uv sync --frozen --package ingestion --no-dev --no-install-workspace

#copy actual code after the dependencies are installed to avoid cache busting
COPY common ./common
COPY ingestion/src ./ingestion/src

# final sync to link the local code
RUN --mount=type=cache,id=ingestion-uv-cache,target=/root/.cache/uv \
    uv sync --frozen --package ingestion --no-dev



