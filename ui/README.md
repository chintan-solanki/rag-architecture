# RAG Streamlit UI

The UI provides document submission and question answering through the RAG API.
It does not perform ingestion, retrieval, or generation itself.

## Configuration and launch

Set `RAG_API_BASE_URL` to the root URL of the reachable API (without `/api/v1`),
then run Streamlit from the repository root:

```bash
export RAG_API_BASE_URL=http://localhost:8000
uv run streamlit run ui/app.py
```

## Run with Docker Compose

The UI service is defined in the root Compose file. From the repository root,
start the existing services and UI together:

```bash
docker compose up --build
```

Compose publishes Streamlit on <http://localhost:8501> and configures its
server-side API client to use `http://api:8000` on the shared Compose network.
Only the UI service definition was added; other service behavior is unchanged.

To build just the UI image from the repository root:

```bash
docker build -f ui/Dockerfile -t rag-ui .
```

The image expects `RAG_API_BASE_URL` to point at an API address reachable from
the container. The browser stores its generated client ID in local storage;
the ID is not an editable UI setting.

The UI sends the client ID in both underscore and hyphen header spellings.
For the current ingestion-events route, which declares `x_client_id` as a
query parameter rather than a header, it also sends the ID as that query
parameter so the API can scope the stream. The ID is a random browser
identifier, not an authentication credential.

## Tests

Run the focused UI tests from the repository root:

```bash
uv run python -m unittest discover -s ui/tests -v
```
