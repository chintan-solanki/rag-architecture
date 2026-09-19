# RAG Service — Final Requirements Specification

## 1. Purpose

Implement a FastAPI-based `ragservice` that provides two capabilities:

1. **RAG query**

   * Retrieve relevant chunks from the existing Qdrant collection.
   * Generate an answer using an LLM.
   * Provide source references and citation information.
   * Support both non-streaming and streaming responses.

2. **Document ingestion**

   * Accept PDF uploads or URLs.
   * Integrate with the existing Kafka-based ingestion pipeline.
   * Preserve the existing parsing, chunking, indexing, and content-hash deduplication behavior.

The service is a local POC. The implementation should favor straightforward, maintainable components over production-scale abstractions.

---

# 2. API Base Path

All API endpoints must use the versioned prefix:

```text
/api/v1
```

No authentication or authorization is required for this POC.

---

# 3. Query API

## 3.1 Non-streaming query

Endpoint:

```http
POST /api/v1/query
```

The request contains:

* user query text
* search configuration

Example:

```json
{
  "query": "What was TCS revenue growth in FY2025?",
  "search_type": "hybrid"
}
```

`search_type` must initially support:

```text
dense
bm25
hybrid
```

The design should allow additional search settings to be added later.

The service performs:

```text
HTTP request
    ↓
request validation
    ↓
Qdrant retrieval through LlamaIndex
    ↓
construct source references/context
    ↓
LLM generation
    ↓
CitationProcessor
    ↓
construct QueryResponse
    ↓
HTTP response
```

---

# 4. Streaming Query API

Endpoint:

```http
POST /api/v1/query/stream
```

The endpoint uses Server-Sent Events (SSE).

The LLM itself produces a **normal text stream**, not a Pydantic/JSON structured output.

The LLM is instructed to represent citations inline using:

```text
[[cite]][1,2]
```

For example:

```text
TCS reported strong revenue growth [[cite]][1,2].
```

The API passes each incoming LLM chunk through `CitationProcessor`.

For each LLM chunk:

```python
extracted_text, citations = citation_processor.add_chunk(src_chunk)
```

The `extracted_text` returned by `add_chunk()` is a **delta**, not the complete accumulated answer.

The API streams this extracted text to the client.

Therefore, if the LLM produces `n` chunks, the API produces:

```text
n answer-delta SSE events
+
1 final SSE event
```

The final event contains the complete `QueryResponse`.

The UI therefore does not need to:

* parse partial JSON;
* understand LLM structured output;
* run Instructor or an equivalent library;
* process citation syntax;
* diff accumulated responses.

The UI only needs to append streamed answer text and then process the final authoritative `QueryResponse`.

---

# 5. Streaming Event Contract

The streaming API should use explicit SSE event types.

Conceptually:

```text
event: answer_delta
data: {"text": "TCS reported"}

event: answer_delta
data: {"text": " strong revenue growth."}

...

event: completed
data: {
    "answer": ...,
    "sources": ...
}
```

`answer_delta` contains only the extracted text returned by `CitationProcessor.add_chunk()`.

Citation markers such as:

```text
[[cite]][1,2]
```

must not be sent to the UI.

The `completed` event contains the complete `QueryResponse`.

The final response is authoritative and can be used by the UI to replace/reconcile the temporary streamed representation.

---

# 6. QueryResponse

The API should expose a structured response model.

The response is conceptually:

```python
class Citation(BaseModel):
    source_id: int


class AnswerPart(BaseModel):
    text: str
    citations: list[Citation]


class Source(BaseModel):
    id: int
    chunk_id: str
    document_id: str
    text: str
    section_title: str | None = None
    file_name: str | None = None
    file_title: str | None = None
    file_author: str | None = None
    chunk_start_page_idx: int | None = None
    chunk_end_page_idx: int | None = None


class QueryResponse(BaseModel):
    answer: list[AnswerPart]
    sources: list[Source]
```

The final response must preserve the relationship between portions of the answer and their supporting sources.

`AnswerPart` is constructed by the API from the processed answer text and citation ranges. It is **not** an LLM structured-output model.

The LLM produces ordinary text; `CitationProcessor` determines where citations occur.

---

# 7. CitationProcessor

A `CitationProcessor` class must exist under the `helpers` folder.

The API must treat it as the component responsible for parsing the citation syntax emitted by the LLM.

## 7.1 `add_chunk`

Signature conceptually:

```python
add_chunk(src_chunk: str) -> tuple[str, list[tuple[int, int, list[int]]]]
```

It accepts one streamed LLM text chunk.

It returns:

```text
extracted_text
citations
```

`extracted_text` is the text delta that should be forwarded to the client.

Each citation is represented by:

```text
(block_start_index, block_end_index, id_list)
```

For example:

```python
(2, 60, [1, 2])
```

means:

```python
citation_processor.target_text[2:60]
```

is associated with source IDs:

```text
1
2
```

The indexes refer to the accumulated `target_text`, not to an individual streamed chunk.

The processor must therefore correctly handle citation syntax that may span multiple LLM chunks.

---

## 7.2 `end_src_stream`

The processor exposes:

```python
end_src_stream()
```

This ends processing of the source stream and returns nothing.

After the complete LLM stream has been processed, the API reads:

```python
citation_processor.target_text
citation_processor.all_citations
```

---

## 7.3 Processor state

The processor has two instance properties:

```python
target_text
all_citations
```

`target_text` contains the complete extracted answer text after citation syntax has been removed.

`all_citations` contains all citation triplets:

```text
[
    (start_index, end_index, [source_ids]),
    ...
]
```

---

# 8. Citation IDs

Citation IDs are **local to a query**.

Before calling the LLM, the API assigns local IDs to the retrieved source references:

```text
[1] source A
[2] source B
[3] source C
```

The same IDs are supplied to the LLM in its context.

When the LLM emits:

```text
[[cite]][1,3]
```

the IDs refer to those source references only.

They are not:

* Qdrant point IDs;
* document IDs;
* chunk IDs;
* globally persistent citation IDs.

The API maps these local citation IDs back to the corresponding `Source` objects when constructing `QueryResponse`.

---

# 9. Citation Validation

The API should ensure that citation IDs produced by the LLM refer only to sources supplied to that LLM request.

Invalid/nonexistent source IDs must not result in references to arbitrary sources.

Citation validation should be performed inside the API/citation-processing layer rather than delegated to the UI.

The exact handling of malformed citation syntax or invalid IDs should be encapsulated by the citation-processing implementation.

---

# 10. Retrieval

`ragservice` performs retrieval directly against the existing Qdrant collection using LlamaIndex.

Initial search types:

```text
dense
bm25
hybrid
```

The service must construct the source list from the retrieved nodes.

The source IDs exposed to the LLM and final API response are local sequential identifiers for the current query.

The API should not expose internal container paths such as:

```text
/app/staging/fetched/...
```

as part of the public source representation.

---

# 11. Qdrant

The existing Qdrant collection is used.

Current collection:

```text
hybrid_collection
```

The existing vector configuration contains:

* dense vector: `text-dense`
* sparse vector: `text-sparse-new`

The service should use the existing collection rather than creating a separate query-time collection.

---

# 12. LLM

The POC will use an OpenAI model through the existing LLM stack.

The model name/configuration must be configuration-driven rather than hard-coded into the application.

A multi-provider abstraction is not required for v1.

The LLM must be instructed to:

* answer using the supplied retrieved context;
* use only supplied source IDs for citations;
* emit citations using the agreed syntax:

```text
[[cite]][1,2]
```

* avoid inventing source IDs.

The LLM produces **regular text**, not a structured `QueryResponse`.

---

# 13. No Structured LLM Output

The query-generation path must not depend on:

* Instructor;
* Pydantic structured-output generation by the LLM;
* incremental JSON parsing;
* partial structured-response diffing.

Pydantic models are still used by the API for its request/response contracts.

The distinction is:

```text
LLM output:
ordinary text + citation markers

API:
CitationProcessor → structured QueryResponse
```

This keeps streaming straightforward while retaining a structured API contract.

---

# 14. Empty Retrieval Result

If retrieval produces no relevant sources, the RAG service should return an empty response rather than attempting to generate an unsupported answer.

The intended behavior is:

```python
QueryResponse(
    answer=[],
    sources=[]
)
```

The UI is responsible for deciding how to communicate the absence of relevant results to the user.

---

# 15. Source Metadata

The final `Source` representation should contain enough information for the UI to display useful provenance.

At minimum:

```text
id
chunk_id
document_id
text
section_title
file_name
file_title
file_author
chunk_start_page_idx
chunk_end_page_idx
```

Relevance score is intentionally excluded from v1.

Character offsets are also not part of the current public `Source` contract unless required later by the UI.

Internal Qdrant metadata may contain additional fields; these do not automatically need to be exposed through the API.

---

# 16. Document Ingestion API

Endpoint:

```http
POST /api/v1/documents
```

The endpoint accepts either:

1. a PDF file upload; or
2. a URL pointing to a PDF.

The endpoint is asynchronous and returns:

```http
202 Accepted
```

with the generated `document_id`.

The existing ingestion pipeline remains responsible for downloading, parsing, chunking, and indexing.

---

# 17. Document IDs

`document_id` is the identifier propagated through the ingestion pipeline.

The ownership rules are:

### URL ingestion

`ragservice` generates the `document_id`.

```text
API
 ↓
document_download_requested
 ↓
downloader
 ↓
document_fetched
 ↓
existing ingestion pipeline
```

The downloader preserves the supplied `document_id`.

### API file upload

`ragservice` generates the `document_id`.

Because the existing filewatcher watches the incoming directory rather than Kafka, the ID must be carried through the uploaded filename.

The proposed convention is:

```text
{document_id}_{original_filename}.pdf
```

The filewatcher extracts the ID and propagates it.

### Direct file drop

If a file is placed directly into the incoming directory without an API-generated ID, the existing filewatcher generates the `document_id`.

Downstream workers must preserve the existing ID rather than generating new document IDs.

---

# 18. URL Ingestion

For a URL request, `ragservice` publishes a Kafka event requesting the downloader to fetch the document.

Conceptually:

```json
{
  "event_type": "document_download_requested",
  "document_id": "...",
  "url": "https://..."
}
```

The downloader:

1. downloads the PDF;
2. stores it under:

```text
/app/staging/fetched
```

3. uses the required filename convention;
4. publishes the existing `document_fetched` event;
5. preserves the original `document_id`.

The exact existing event field names should be standardized around `document_id` rather than introducing multiple equivalent identifiers such as `file_id` or `unique_id`.

---

# 19. Downloaded Filename

Downloaded files should use:

```text
{document_id}_{file_name_from_url}.{suffix}
```

The downloader is responsible for generating the final fetched filename.

Only PDF documents are supported in v1.

---

# 20. Existing Ingestion Pipeline

The existing ingestion pipeline remains responsible for:

```text
incoming
   ↓
filewatcher
   ↓
fetched
   ↓
document_fetched
   ↓
parser
   ↓
chunker
   ↓
indexer
   ↓
Qdrant
```

`ragservice` should not duplicate this processing logic.

The existing content-hash-based deduplication behavior remains unchanged.

---

# 21. Duplicate Documents

Deduplication continues to be based on **document content hash**, not filename or URL.

For URL ingestion, the downloader may download content that has already been indexed.

The downstream indexer/database performs the existing content-hash check and skips already-indexed content.

No URL-level deduplication is required for v1.

---

# 22. Ingestion Status

A document-status endpoint is explicitly **out of scope for v1**.

Do not implement:

```text
GET /api/v1/documents/{document_id}/status
```

Persistent ingestion lifecycle status is also out of scope for this version.

A future version may introduce lifecycle statuses such as:

```text
RECEIVED
FETCHED
PARSED
INDEXED
FAILED
```

and potentially an SSE status stream, but this should not be implemented now.

---

# 23. OpenTelemetry

OpenTelemetry instrumentation is required for the **query endpoints only**.

Ingestion tracing is out of scope for v1.

Important query stages should have useful spans, including where applicable:

```text
HTTP request
    ↓
retrieval
    ↓
Qdrant interaction
    ↓
context construction
    ↓
LLM generation
    ↓
citation processing
    ↓
response construction
```

Telemetry must not indiscriminately record complete:

* user queries;
* LLM prompts;
* LLM responses;
* retrieved source text;

as span attributes.

The implementation should favor useful operational metadata while avoiding unnecessarily large or sensitive telemetry payloads.

---

# 24. Configuration

Configuration must be environment/configuration driven.

At minimum, configuration should cover:

* LLM model;
* OpenAI API configuration;
* Qdrant connection;
* Qdrant collection;
* Kafka connection;
* relevant staging paths;
* application configuration.

Secrets such as API keys must not be hard-coded.

The configuration approach should allow the service to run both:

```text
inside Docker
```

and:

```text
directly from the development environment
```

without requiring application-code changes.

---

# 25. Docker/Runtime Integration

The service should integrate with the existing Docker Compose environment.

Relevant existing services include:

```text
ragservice
kafka
qdrant
ingestion
```

The service should communicate with other Compose services using their Compose service names rather than `localhost`.

For example:

```text
qdrant:6333
```

rather than:

```text
localhost:6333
```

when running inside the Compose network.

---

# 26. Error Handling

The API should provide normal HTTP errors for request-level failures such as:

* invalid request;
* unsupported file type;
* malformed URL;
* invalid search type;
* unavailable required backend.

For streaming failures, the API should terminate the SSE stream with an appropriate error event rather than silently leaving the client waiting indefinitely.

The precise error-event schema can remain small for the POC.

---

# 27. Out of Scope for V1

The following are explicitly excluded:

* authentication/authorization;
* ingestion status API;
* persistent ingestion progress tracking;
* ingestion OpenTelemetry;
* document deletion;
* document replacement/update;
* non-PDF ingestion;
* multi-turn conversational memory;
* reranking;
* relevance-score exposure;
* multiple LLM-provider abstraction;
* sophisticated citation verification beyond validating source IDs and citation ranges;
* UI implementation;
* structured LLM output;
* Instructor-based structured streaming;
* UI-side partial JSON processing.

---

# 28. Final High-Level Architecture

```text
                         ┌──────────────────────┐
                         │       FastAPI        │
                         │      ragservice      │
                         └──────────┬───────────┘
                                    │
                 ┌──────────────────┴──────────────────┐
                 │                                     │
                 ▼                                     ▼
          Query endpoints                       Document endpoint
                 │                                     │
                 ▼                                     ▼
          LlamaIndex retrieval                    Kafka / staging
                 │                                     │
                 ▼                                     ▼
              Qdrant                              Downloader /
                 │                                 filewatcher
                 ▼                                     │
          Retrieved sources                            ▼
                 │                               Existing ingestion
                 ▼                                     │
        ┌─────────────────┐                           ▼
        │       LLM       │                         Qdrant
        │ regular text +  │
        │ citation blocks │
        └────────┬────────┘
                 │
                 │ streamed text
                 ▼
        ┌─────────────────────┐
        │  CitationProcessor  │
        └──────────┬──────────┘
                   │
          ┌────────┴─────────┐
          │                  │
          ▼                  ▼
    extracted_text      target_text +
          │             all_citations
          │                  │
          ▼                  ▼
       SSE deltas       QueryResponse
          │                  │
          └────────┬─────────┘
                   ▼
                  UI
```

The central design principle for the query path is:

> **Stream ordinary answer text for responsiveness; keep citation parsing and structured response construction entirely inside `ragservice`; send the complete authoritative `QueryResponse` at the end.**

This avoids structured-output streaming complexity while retaining a structured API contract and robust source/citation relationships.
