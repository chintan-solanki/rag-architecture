# RAG Streamlit UI — Implementation Plan

## 1. Goal and scope

Implement the two workflows in [`requirements.md`](./requirements.md) as a Streamlit client of the existing RAG API:

1. Submit one PDF upload or PDF URL for asynchronous ingestion and show live progress.
2. Submit one question at a time, render answer deltas as they arrive, then show the authoritative cited answer and supporting sources.

The UI must not implement parsing, indexing, retrieval, or generation. Do not add authentication, persistent conversation history, document management, PDF opening/highlighting, or other features listed as out of scope.

All implementation files and configuration changes belong under `ui/`. The API is a reference for the wire contract; do not change API behavior as part of this UI work. This document is an implementation plan only and does not change application code.

## 2. Current project and API facts

- The UI implementation consists of `app.py`, `config.py`, `api_client.py`, `sse.py`, `state.py`, `query_response.py`, `pages/`, and `components/`; `README.md` documents launch configuration, and `tests/` contains focused transport, parser, and citation tests.
- The UI package already depends on Streamlit. The implementation can use Python's standard-library HTTP/SSE support and a small local-storage Streamlit component, avoiding additional runtime dependencies.
- The API is mounted under `/api/v1` and exposes:
  - `POST /documents`: multipart form with exactly one of `file` or `url`; responds `202` with `{"ingestion_id": ...}`.
  - `GET /documents/events`: SSE event stream; the current router reads `x_client_id` as a query parameter.
  - `POST /query/stream`: JSON request with `query`, `retrieval_config`, and `generation_config`; streams `answer_delta`, `completed`, and potentially `error` events.
- Ingestion events contain `ingestion_id`, `document_id`, `client_id`, `status`, `stage`, and `error`. The current event route may initially emit in-progress records from storage, then live pub/sub updates. No event ID or replay cursor is defined.
- The ingestion service requires a non-empty client ID in practice. Always send `x_client_id` on document submission and ingestion-event requests.
- In the current API router, the upload endpoint's `Header()` parameter uses FastAPI's hyphenated header alias, while the ingestion-event endpoint currently receives `x_client_id` as a query parameter. The UI should send both header spellings and include the query parameter on the event stream until the API contract is aligned.
- The query route currently does not declare or use `x_client_id`. Send the header on the query request if maintaining the common UI request-header convention, but do not assume the current API scopes queries by it.
- The API's source model allows optional filename, title, author, section title, and page indices. The ingestion/indexing code records page indices as zero-based; convert each available index to one-based PDF page numbers for display.
- The source response uses integer IDs, and each answer block's citations refer to those IDs. An empty answer or empty source list is a valid API response.

## 3. Proposed UI structure

Keep the implementation small, with a single application shell and focused page/API helpers:

```text
ui/
  app.py                       # config, client identity, sidebar navigation, routing
  config.py                    # validated API base URL
  api_client.py                # document, query, and SSE HTTP operations
  sse.py                       # incremental SSE framing and JSON decoding
  state.py                     # session-state keys and query/ingestion state helpers
  query_response.py            # completed-query response validation
  pages/
    add_documents.py           # upload/URL form and ingestion activity
    ask_questions.py           # settings, input, streamed and completed answer
  components/
    client_identity.py         # browser-local-storage integration
    citations.py               # answer citation rendering and source details
  tests/
    test_sse.py
    test_api_client.py
    test_citations.py
```

This is a suggested split, not a requirement to create empty abstractions. Keep helpers only where they own reusable behavior or make streaming/state logic testable. Keep the API base URL in one configuration source, and keep presentation code out of the HTTP/SSE parser.

Use a single sidebar page selector in the app shell (or an equivalent navigation mechanism that runs a page-transition hook). A centralized transition hook makes it possible to stop the ingestion listener when the user leaves Add Documents, as required.

## 4. Implementation sequence

### Step 1 — Configuration and API client

1. Add a configuration reader for `RAG_API_BASE_URL`, sourced from environment/application configuration. Normalize trailing slashes and fail visibly with a clear setup message if it is missing or malformed. Do not embed endpoint hostnames in individual page components.
2. Construct endpoint URLs from the configured base URL and the `/api/v1` prefix in one place.
3. Use standard-library HTTP helpers with explicit bounded timeouts. Use streaming mode for SSE connections and always close responses on completion or cancellation.
4. Implement typed, narrow API operations:
   - Upload: `multipart/form-data`, `file` field, `x_client_id` header.
   - URL submission: form-encoded/multipart `url` field, `x_client_id` header.
   - Ingestion events: streaming GET with `x_client_id`.
   - Query: JSON POST with `query`, `retrieval_config`, and `generation_config`, plus `x_client_id` if following the common request-header convention.
5. Check HTTP status before decoding a success body. For document acceptance, validate that `ingestion_id` is present and non-empty. Surface useful API error detail when available; do not turn malformed or failed responses into success-shaped values.
6. Keep transport on the Python standard library unless a concrete limitation requires another package; do not add runtime dependencies solely for HTTP or local storage.

### Step 2 — Browser identity and shared session state

1. Implement browser-local-storage access for `client_id` using a small Streamlit component. Streamlit session state alone is insufficient because it does not persist through a browser refresh.
2. On first load, read the stored value; if absent, create a UUID in the browser using the browser's cryptographic random UUID facility and persist it. Return the value to Streamlit and cache it in session state for the current run.
3. Do not render the ID as an editable control. Disable API actions until identity initialization has completed successfully; report identity/component failures rather than submitting requests without a client ID.
4. Initialize independent session state for retrieval and generation settings (retrieval type defaults to `hybrid`, Top K to `3`, candidate pool to `10`, alpha to `0.5`, re-ranking enabled, temperature `0.1`, Top-p `1.0`), current question, streamed text, final structured result, active-query flag, ingestion event list, and ingestion-listener lifecycle.
5. On page changes, preserve the client identity and search settings. Clear/replace query results only when a new question is submitted. Keep the ingestion event list ephemeral and session-scoped.

### Step 3 — Sidebar navigation and app shell

1. Add the application title and sidebar choices **Add Documents** and **Ask Questions**.
2. Route to exactly one page for each rerun. Track the active page in session state.
3. When leaving Add Documents, signal the ingestion listener to stop and close its active response. When entering it, create at most one listener for this session.
4. Keep navigation independent of the client ID and search settings; switching pages must not regenerate or reset either.

### Step 4 — Add Documents page

1. Divide the page into **Add Document** and **Ingestion Activity**.
2. Offer mutually exclusive local-file and URL inputs (for example, tabs or a radio control) so one submission cannot accidentally send both fields.
3. Configure the file picker for `.pdf`; before sending, reject a missing filename, wrong extension/content type when clearly non-PDF, and empty file. The API remains responsible for authoritative PDF validation.
4. Validate URL syntax locally: require `http` or `https` and a hostname. Do not fetch the URL from the UI to verify its content type.
5. On submit, disable the submit action during the HTTP handoff only. Send exactly one field and the client-ID header. On success, prepend a document-accepted entry with its `ingestion_id` to the Ingestion Activity log. On failure, show the error and keep retry available.
6. Add a single session-scoped SSE reader while this page is active. Run the blocking network read outside Streamlit's render thread; send decoded events to the page through a thread-safe queue. The Streamlit page/fragment drains the queue and updates `st.session_state`; the worker must not mutate Streamlit UI/session state directly.
7. Parse SSE by protocol framing (`event:`/`data:` lines, blank-line event boundary, multi-line data), decode JSON payloads (including JSON strings containing a second JSON-encoded payload), and validate expected event fields before queueing. The endpoint may provide plain/default SSE data rather than useful named event types, so derive the event from the JSON payload and do not require a specific SSE event name.
8. Prepend each accepted-submission entry and valid stream event so the newest is always at the top. Show the empty-activity placeholder only when the activity log is empty. Put the log in a fixed-height, scrollable container and use compact event cards. Display ingestion ID, filename when available, stage, status, and error for failed events. Prefer a user-facing filename from event/document information; when only `document_id` is supplied, display it without pretending it is a filename.
9. Style `completed` green, `failed` red, and `in-progress` with normal text. Do not rewrite or reinterpret the API's stage string.
10. On disconnect or transient network failure, show a non-blocking connection state and reconnect with bounded backoff while the page is active. Stop retries on navigation/session shutdown. Since IDs/replay are absent, accept that events can be lost on refresh or a connection gap; do not claim durable history. Do not silently suppress parsing or connection errors.

### Step 5 — Ask Questions page and query streaming

1. Render **Search Settings** above the question field:
   - First row: retrieval type (`hybrid`, `dense`, `bm25`) in the first half and an alpha slider (`0`–`1`, default `0.5`) in the second half, shown only for hybrid, with the adjacent label "dense weight, Relative Score Fusion".
   - Second row: Top K combobox (`1`–`10`, default `3`), centered **Use re-ranker** checkbox (default checked), and candidate pool size when re-ranking is enabled. Candidate pool defaults to `10`.
   - Generation row: temperature slider (`0`–`1`, default `0.1`) and Top-p slider (`0.5`–`1.0`, default `1.0`).
   - Persist all settings in session state so they survive reruns and page navigation.
2. Provide a compact multiline question input with placeholder `Ask a question!` and an **Ask question** button to its right. Keep the input about two lines high. Trim only for empty-input validation; submit the user's entered question otherwise.
3. On valid submission, first replace/clear previous query state, store the submitted question, and mark a query active. Disable Ask until the stream ends or errors.
4. POST the current question and complete retrieval and generation settings to `/api/v1/query/stream` using this shape:

   ```json
   {
     "query": "question text",
     "retrieval_config": {
       "retrieval_type": "hybrid",
       "use_reranker": true,
       "top_k": 3,
       "candidate_pool_size": 10,
       "alpha": 0.5
     },
     "generation_config": {
       "temperature": 0.1,
       "max_output_tokens": 512,
       "top_p": 1.0
     }
   }
   ```

   Set hidden conditional retrieval fields to `null`. The API passes the
   configurations to the retrieval and generation services, but does not yet
   apply the candidate-pool, alpha, re-ranker, or generation options to their
   algorithms.

5. Read and decode SSE events incrementally. Append each `answer_delta.data.text` to the streamed text and immediately rerender the accumulated plain answer. Handle an API `error` event as an incomplete stream failure. Stop at the first valid `completed` event.
6. On normal stream termination without `completed`, preserve streamed text, display a clear incomplete-answer error, do not create citations/sources, and restore the Ask control. For HTTP errors, display the error in the answer area with no stale prior result.
7. Parse the final event into a validated response representation before rendering. If parsing or validation fails, preserve streamed text, report that the structured response was invalid, omit all citations and sources, and allow another query.
8. Treat `completed` as authoritative: render the final answer from answer blocks (including citations), not from accumulated delta text. If there are no answer blocks/text, show a clear empty-result message. A valid no-source response should still display its answer.

### Step 6 — Final answer, citations, and sources

1. Lay out completed results as two vertical columns. In the left column, show the submitted question in a right-aligned user-style bubble followed by the answer. In the right column, show sources only when the final response includes sources.
2. Render answer blocks in API order. For each block, render its text, then place one citation control immediately after it if and only if citations are present. Blocks with empty citation lists render normally.
3. Resolve each citation's `source_id` against the final `sources` list. Preserve API citation ordering. Validate mappings before rendering; do not fabricate a filename or silently link an unknown source. If the response violates the ID-reference contract, show a structured-response warning and avoid misleading citation controls.
4. Label a one-source citation with that source's `original_file_name`, falling back to `file_name`; for multiple sources use the first source filename followed by `+N` where N is the number of additional sources (for example, `[OCI_faq.pdf +2]`). Define a neutral fallback label when both are absent, without changing the source mapping.
5. Provide a theme-aware hover/focus popover for each citation. Show previous/current/next navigation and the source count in its header, then show only the selected source's filename, optional document title and page range, and complete source text rendered as CommonMark Markdown. Use a fixed viewport-aware height capped at 24rem consistently across sources, with scrolling for longer source content; do not truncate Markdown source before rendering. Do not display author or section names. Use one-based page display (`chunk_start_page_idx + 1` through `chunk_end_page_idx + 1`) for the current zero-based API convention. Omit absent metadata, and handle either page bound being absent without rendering an empty range.
6. Use a reusable citation component or a supported frontend technique that genuinely provides hover details. Escape API-provided text and metadata if generating HTML; do not interpolate source content into unsafe markup. The click action must remain informational/no-op and must not imply PDF navigation.
7. Render the right-hand source list in API order with filename and one-based page conversion, but show full source text as CommonMark Markdown with pipe-table support. Do not display author or section names, and do not render an empty panel when there are no sources.

### Step 7 — Error and lifecycle handling

1. Keep expected failures distinct: document-submit HTTP error, ingestion SSE interruption/reconnect, query HTTP error, query `error` event/early close, malformed SSE JSON, and invalid completed payload.
2. Show actionable but non-sensitive error text in the relevant section. Preserve only streamed answer text for an incomplete query; never display stale prior sources/citations after a new submission.
3. Use `try/finally` around streaming response lifecycles to close network resources and clear the active-query/listener flags.
4. Prevent duplicate ingestion workers and overlapping query submissions through explicit session state/locks. Keep queue and cancellation primitives thread-safe.
5. Do not catch broad exceptions and continue as if successful. Catch expected transport, decoding, and validation exceptions at the boundaries, surface them to the user, and log enough diagnostic context for development without logging full uploaded documents, source bodies, or secrets.

## 5. API request and response contract checklist

| Operation | Request | Successful behavior |
|---|---|---|
| Upload PDF | `POST /api/v1/documents`, multipart `file`, `x_client_id` | Read non-empty `ingestion_id`; acknowledge accepted job, then rely on events |
| Submit PDF URL | `POST /api/v1/documents`, form `url`, `x_client_id` | Same as upload; URL must be HTTP(S) with host |
| Monitor ingestion | `GET /api/v1/documents/events`, `x_client_id`, SSE | Append valid event payloads in receive order; reconnect while page active |
| Ask question | `POST /api/v1/query/stream`, JSON body above | Render deltas, then replace with validated completed response |

The query route currently ignores client identity because it does not accept the header as a parameter; document this as a current API limitation, not as UI-side session isolation. The API returns zero-based page indexes from ingestion, while the UI displays one-based PDF pages. The current event endpoint may replay in-progress records when a connection is established; with no event IDs, the UI should not promise exact-once delivery.

## 6. Verification plan

### Automated tests

1. **SSE parser:** blank-line boundaries, comments/keep-alives, multiple `data:` lines, CRLF/LF, final unterminated event, malformed JSON, `answer_delta`, `completed`, and `error`.
2. **Payload/request tests:** exact upload/URL field exclusivity and headers; query body values and top-k bounds; URL schemes/hostname; no empty question submission.
3. **Citation tests:** citation label for one/multiple sources; citation/source order; empty citations; unknown source ID; absent filenames/author/page data; zero-based-to-one-based conversion; normalized/truncated preview.
4. **State/navigation tests:** client identity reuse, persistent search settings, clearing old query result at new submission, single active query/listener, and listener stop on leaving Add Documents.
5. **Failure tests:** HTTP submission failures, stream failure before completion, explicit query `error`, malformed completed payload, and empty answer/no-source valid completion.

Use the repository's existing Python/uv test workflow and add only focused tests for the new UI helpers. Keep tests hermetic by injecting/mock-serving API responses rather than calling a live RAG service.

### Manual end-to-end acceptance

1. Configure `RAG_API_BASE_URL`, start the UI, and confirm first-load client ID creation. Refresh and navigate between pages; confirm the browser ID and search settings remain stable.
2. Submit an invalid file and malformed URL; confirm they are rejected locally and no request is sent.
3. Submit one PDF upload and one PDF URL in separate operations; confirm API acceptance is acknowledged immediately and each event displays under its own ingestion ID with status styling.
4. Simulate or cause an ingestion SSE interruption; confirm reconnection is attempted while Add Documents remains active and stops after navigation away.
5. Ask a non-empty question with each search type and representative top-k values; verify the exact payload and incremental plain-text updates.
6. Verify completed answer block order, citation labels and hover details, source order/content, and one-based displayed page numbers.
7. Verify empty answer, no sources, uncited answer blocks, query HTTP error, explicit stream error, early EOF, and malformed completed data. Confirm no previous answer or citation survives a new failed query.
8. Confirm there is only one active query at a time and no historical conversation or persisted ingestion-history UI has been added.

## 7. Definition of done

- Both sidebar workflows operate end-to-end against the configured API.
- One stable browser-local client ID is used for ingestion submission and monitoring.
- Ingestion events append in receive order and reconnect only while the Add Documents page is active.
- Search settings persist across reruns and page changes; query response is streamed and finalized from the completed event.
- Citation and source displays honor ordering, optional metadata, empty-result behavior, and page-index conversion.
- Expected network, stream, and schema errors are visible and do not leave stale or success-shaped output.
- Focused automated tests and the manual acceptance checklist pass.
- No API/backend code or feature outside the specified UI scope is changed.
