# RAG Service Implementation Plan

## 1. Objective and scope

Implement the local `ragservice` FastAPI application described in
`requirements.md`. The service will:

- expose versioned query and document-ingestion endpoints under `/api/v1`;
- retrieve context from the existing `hybrid_collection` Qdrant collection
  through LlamaIndex;
- generate ordinary text with an OpenAI-backed LLM;
- parse inline citations inside the API and return structured query results;
- stream citation-free answer deltas over SSE and send one authoritative final
  response (which should have the citations as well);
- accept PDF uploads or PDF URLs and hand ingestion work to the existing
  Kafka/filewatcher/ingestion pipeline.

This is a POC implementation. Keep the design modular and testable without
introducing production-scale abstractions, authentication, persistent job
tracking, or unsupported features listed in the requirements. Follow SOLID 
principles wherever applicable.

## 2. Current repository constraints to preserve

- `api/src/main.py` is currently a minimal FastAPI skeleton.
- `api/src/helpers/citationprocessor.py` already contains an incremental
  citation parser. Use it as a black box for now. Can be reviewed later if the user asks.
- Ingestion service currently consumes `document_fetched` Kafka messages containing
  `file_id` and `source_path`.
- The filewatcher currently generates IDs for direct file drops and copies
  files from `staging/incoming` to `staging/fetched`. 
- The ingestion indexer already targets Qdrant collection
  `hybrid_collection`, enables hybrid storage, and writes chunk/page metadata.
- The existing content-hash deduplication in the ingestion worker must remain
  the source of truth.
- Compose currently defines Kafka, Qdrant, filewatcher, and ingestion, but no
  `ragservice` service. Container service names, not `localhost`, must be used
  for in-network connections.

## 3. Target module layout

Create a small set of cohesive modules under `api/src`:

```text
api/
   config/
      config.yml                 # app config settings
   src/
      main.py                    # application factory and router registration
      models/
         query.py                 # request/response and SSE payload models
         documents.py             # document-ingestion request/accepted response models
      routers/
         query.py                 # POST /query and POST /query/stream
         documents.py             # POST /documents
      services/
         retrieval.py             # LlamaIndex/Qdrant retrieval and source mapping
         generation.py            # regular-text LLM prompt and generation/streaming
         query_service.py         # orchestration and QueryResponse construction
         ingestion_service.py     # upload staging and Kafka publication
      helpers/
         citationprocessor.py     # incremental citation parsing/validation
         citations.py              # citation-range to AnswerPart conversion
         kafka.py                  # producer lifecycle and event publication
      telemetry.py               # query-only OpenTelemetry spans
```

Keep imports and public interfaces explicit. Avoid coupling FastAPI route
handlers directly to Qdrant, Kafka, or the LLM client so unit tests can inject
fakes. 

## 4. Phase 1: configuration and dependencies

1. Read app specific configs from config.yml file. Examples include
   - qdrant collection name;
   - Kafka bootstrap servers and publish/subscribe topics;
   - incoming/fetched staging directories;
   - application host/port and optional retrieval settings. 
2. Read secrets and other environment settings from the existing .env file at the project root. Examples include
   - OpenAI API key/base URL and model name;
   - Qdrant URL 
3. Use your judgement in deciding if a setting should be an app config or environment setting. 
   Use safe local defaults where appropriate.
   Use Compose defaults such as `qdrant:6333` and `kafka:9092` for container
   execution, while allowing host-development overrides without code changes.
4. Add only the dependencies required by the implementation, including the
   LlamaIndex Qdrant integration, OpenAI LLM integration, multipart uploads,
   SSE response support, and OpenTelemetry instrumentation/exporter support.
5. Keep secrets out of source control and do not hard-code model names or API
   keys. store secretes in .env file at the root (already available)
6. Add an API container definition to Compose with the API source, staging
   directory, and any model/cache mounts it needs. Add health/readiness
   ordering only where it is supported by the existing Compose setup.

## 5. Phase 2: API models and application wiring

1. Define request models:
   - `QueryRequest` with required query text and an enum/literal for
     `dense`, `bm25`, and `hybrid`;
   - an extensible search-configuration object so future settings can be added
     without changing the endpoint shape;
   - a document request representation that supports either one PDF upload or
     one URL, but rejects ambiguous or empty input.
2. Define response models exactly around the required contract:
   - `Citation(source_id)`;
   - `AnswerPart(text, citations)`;
   - `Source` with local `id`, chunk/document IDs, text, section/file metadata,
     and optional page indexes;
   - `QueryResponse(answer, sources)`;
   - accepted document response containing `document_id`.
3. Add an application-level `/api/v1` router and retain a minimal health/root
   endpoint for runtime checks.
4. Return normal FastAPI validation errors for malformed requests and
   unsupported search types/files.
5. Do not add an ingestion status route, authentication, deletion/update
   routes, or other explicitly out-of-scope endpoints.

## 6. Phase 3: retrieval and source construction

1. Initialize one configured Qdrant/LlamaIndex retrieval service against the
   existing `hybrid_collection`; do not create a query-time collection.
2. Implement the initial search modes:
   - dense vector retrieval;
   - sparse/BM25 retrieval;
   - hybrid retrieval using the existing dense `text-dense` and sparse
     `text-sparse-new` configuration.
3. Convert retrieved nodes into public `Source` objects with sequential,
   query-local IDs starting at 1.
4. Map metadata defensively:
   - preserve `chunk_id`, document ID, text, section title, file name/title/
     author, and page indexes;
   - omit internal container paths and irrelevant internal payload fields;
   - do not expose relevance scores in v1.
5. Build the LLM context from the same ordered source list and label every
   source with its local ID.
6. If retrieval returns no sources, return `QueryResponse(answer=[], sources=[])`
   immediately and do not call the LLM.
7. Make backend failures explicit as HTTP errors for non-streaming requests and
   explicit SSE error events for streaming requests.

## 7. Phase 4: LLM generation and citation processing

1. Configure a single OpenAI model through settings; do not implement a
   multi-provider abstraction in v1.
2. Create a prompt that instructs the model to:
   - answer only from the supplied context;
   - use only the supplied local source IDs;
   - emit citations exactly as `[[cite]][1,2]`;
   - avoid unsupported or invented IDs;
   - return ordinary text, never JSON or a structured `QueryResponse`.
3. Do not change CitationProcessor implemetation for now. Use it as a black box. Only if the tests fail, consider making fixes without making the full blown changes to the approach.
4. Convert the final processed text and citation ranges into `AnswerPart`
   objects. Preserve the text-to-source relationship, discard invalid source
   references according to the chosen documented policy, and prevent
   out-of-range citation spans.
5. Keep citation parsing and validation in the API; the UI must receive
   citation-free deltas and structured final data.

## 8. Phase 5: non-streaming query endpoint

Implement `POST /api/v1/query` with this sequence:

1. Validate the request.
2. Start query telemetry.
3. Retrieve nodes using the requested search type.
4. Construct query-local sources and context.
5. Return an empty `QueryResponse` for empty retrieval.
6. Generate a complete ordinary-text LLM response.
7. Pass the response through `CitationProcessor`, finalize the stream, and
   construct `AnswerPart` and `Source` models.
8. Return the complete `QueryResponse`.

The route should delegate orchestration to a service class/function and should
not contain provider-specific prompt, Qdrant, or citation parsing logic.

## 9. Phase 6: streaming query endpoint

Implement `POST /api/v1/query/stream` using an SSE response:

1. Validate the request and retrieve/build context before opening generation.
2. Return a stream containing one `answer_delta` event for each incoming LLM
   chunk, using exactly the delta returned by `add_chunk()`.
3. Never send `[[cite]][...]` markers to the client.
4. After the LLM stream ends, call `end_src_stream()`, build the complete
   `QueryResponse`, and emit exactly one `completed` event.
5. Serialize event payloads consistently:
   - `answer_delta`: `{ "text": "<delta>" }`;
   - `completed`: the full `QueryResponse` object.
6. If retrieval, generation, citation parsing, or response construction
   fails, emit a small explicit `error` event and close the stream rather than
   leaving the client waiting.
7. Ensure an empty retrieval result follows the same empty-response semantics
   without attempting unsupported generation.
8. Test chunk counts and event ordering, including empty deltas, split citation
   markers, invalid IDs, and generation errors.

## 10. Phase 7: document ingestion endpoint

Implement `POST /api/v1/documents` as an asynchronous `202 Accepted` endpoint:

1. Accept exactly one input:
   - a multipart PDF upload; or
   - a validated HTTP(S) URL whose resource is intended to be a PDF.
2. Generate a new `document_id` in the API for both accepted input forms.
3. For uploads:
   - validate PDF content/type and filename safely;
   - write to the shared incoming staging directory using
     `{document_id}_{original_filename}.pdf`;
   - let the existing filewatcher publish the downstream event.
4. For URLs:
   - publish a `document_download_requested` Kafka message containing
     `document_id` and URL;
   - do not download, parse, chunk, or index in the API process.
5. Standardize the event contract around `document_id` and preserve it through
   downloader, filewatcher, and ingestion messages. Update the existing
   `file_id` handling only as part of this coordinated integration; provide a
   compatibility migration if existing consumers still require the old field.
6. Ensure the downloader creates
   `{document_id}_{file_name_from_url}.{suffix}` under the shared fetched
   directory, rejects non-PDF content, and publishes the existing fetched
   event with the original ID.
7. Preserve direct file-drop behavior: when no API-generated ID is present, the
   filewatcher may generate one. This will need change to the filewatcher worker inside the ingestion project.
8. Do not add persistent ingestion status, polling, SSE progress, URL-level
   deduplication, or content processing in `ragservice`.
9. Create downloader.py /ingestion/src/workers. 
   - The downloader listens to `document_download_requested` kafka message and downloads and copies the files in the shared incoming staging directory using `{document_id}_{original_filename}.pdf`; 
   - let the existing filewatcher publish the downstream event.

## 11. Phase 8: OpenTelemetry

Instrument query endpoints only. Add useful spans for:

- request validation/orchestration;
- retrieval;
- Qdrant interaction;
- context construction;
- LLM generation;
- citation processing;
- response construction.

Record bounded operational metadata such as search type, source count,
success/failure, and model name where appropriate. Do not attach complete user
queries, prompts, model responses, or retrieved source text to spans. Do not
instrument ingestion in v1.

## 12. Testing and verification plan

Add focused tests before wiring the full runtime:

### Citation processor

- plain text and multiple citations;
- citation markers split at every meaningful boundary across chunks;
- citations spanning multiple answer deltas;
- escaped markers;
- malformed/empty ID blocks;
- duplicate, negative, out-of-range, and nonexistent source IDs;
- correct accumulated indexes and final state after `end_src_stream()`.

### Models and routes

- request validation and search-type rejection;
- exact `QueryResponse` serialization;
- empty retrieval behavior;
- non-streaming orchestration with mocked retrieval and LLM services;
- SSE event names, JSON payloads, event ordering, and final-event count;
- streaming failure/error event behavior.

### Retrieval and generation

- source metadata mapping and local ID assignment;
- no internal staging paths in public sources;
- dense, BM25, and hybrid strategy selection;
- prompt contains only the intended source context and citation instructions;
- no structured-output/incremental-JSON dependency.

### Ingestion

- upload validation and document-ID filename convention;
- URL event payload and `202` response;
- Kafka publication failures are surfaced;
- downloader/filewatcher preserve IDs;
- existing content-hash deduplication remains unchanged.

### Integration checks

- application starts with development-environment settings;
- Compose service-name connectivity works for Kafka and Qdrant;
- API health endpoint responds;
- an end-to-end seeded query returns sources and citations;
- an upload and URL request reach the existing ingestion pipeline.

Use the repository’s existing test/build tooling and run focused tests first,
then the API and ingestion integration checks. Validate that unrelated existing
worktree changes are not modified.

## 13. Delivery sequence

1. Add configuration and dependency wiring.
2. Add typed API models and router/application structure.
3. Implement and test citation processing and answer construction.
4. Implement retrieval and non-streaming query flow.
5. Implement SSE streaming and error events.
6. Implement upload/URL ingestion handoff and event-ID propagation.
7. Add Compose/runtime integration.
8. Add query-only telemetry.
9. Run focused tests, integration checks, and a final scope/diff review.

Each step should leave the service importable and should avoid silently falling
back to fake data or success-shaped responses when a required backend is
unavailable.

## 14. Acceptance criteria

- All implemented endpoints use `/api/v1`.
- `POST /api/v1/query` returns the required structured response.
- `POST /api/v1/query/stream` emits citation-free `answer_delta` events followed
  by exactly one authoritative `completed` event.
- Citation IDs are query-local, validated, and mapped to the returned sources.
- Empty retrieval returns empty answer and source lists without an LLM call.
- Retrieval uses the existing Qdrant `hybrid_collection`.
- The LLM is configuration-driven and emits ordinary text only.
- PDF uploads and PDF URLs return `202` with generated document IDs.
- Existing parsing, chunking, indexing, and content-hash deduplication remain in
  the ingestion pipeline.
- URL and upload document IDs survive the downloader/filewatcher/ingestion
  handoff; direct file drops continue to work.
- Query telemetry is present without recording complete sensitive payloads.
- Explicit out-of-scope features are not implemented.
