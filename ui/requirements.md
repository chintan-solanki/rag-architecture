# RAG Streamlit UI — Requirements Specification

## 1. Purpose

The Streamlit application provides a simple user interface for interacting with the RAG system through the RAG API.

The application supports two primary workflows:

1. **Add Documents** — upload PDF documents or provide PDF URLs for asynchronous ingestion and indexing.
2. **Ask Questions** — ask questions about the indexed documents and receive answers grounded in the retrieved document sources.

The UI should provide a simple, lightweight experience inspired by the basic interaction model of Perplexity, without attempting to reproduce its full feature set.

The application does not perform document parsing, chunking, embedding, retrieval, or LLM generation itself. All RAG functionality is provided by the RAG API.

---

# 2. Application Structure

The application has two pages accessible through the Streamlit sidebar:

* **Add Documents**
* **Ask Questions**

The application maintains a browser/client-level `client_id`. This identifier is used to associate document ingestion activity and query requests with the current user session.

The application does not require user authentication.

---

# 3. Client Identity

## 3.1 Client ID

The UI must maintain a unique `client_id` for the current browser client.

On initial application load:

1. Check whether a `client_id` already exists in browser local storage.
2. If one exists, reuse it.
3. Otherwise, generate a random unique identifier and store it in local storage.
4. The same `client_id` must be used for subsequent API requests from that browser.

The `client_id` should survive:

* Streamlit reruns
* Page navigation
* Browser refreshes

Clearing browser storage may result in a new `client_id`.

The UI must send the client ID using the following HTTP header on API requests that require it:

```text
x_client_id: <client_id>
```

The UI must not expose the `client_id` as a user-editable setting.

---

# 4. API Integration

The UI communicates exclusively with the RAG API for RAG-related operations.

The relevant endpoints are:

```text
POST /api/v1/documents
GET  /api/v1/documents/events
POST /api/v1/query/stream
```

The API base URL must be configurable through application configuration rather than hard-coded into individual UI components.

---

# 5. Add Documents Page

The Add Documents page is used to submit documents for asynchronous ingestion.

The page contains two primary sections:

1. **Add Document**
2. **Ingestion Activity**

---

## 5.1 Add Document Section

The section allows the user to provide a PDF using one of two methods:

* Upload a local PDF file
* Provide a URL pointing to a PDF

The UI should make the two alternatives clear, for example using a file uploader and a URL input.

Only one document should be submitted per operation.

### File upload

The file uploader must accept PDF files.

The UI should reject or prevent submission of files that are clearly not PDFs.

When a local PDF is submitted, the UI sends it to:

```text
POST /api/v1/documents
```

using `multipart/form-data` with the `file` field.

### PDF URL

The user may alternatively enter a URL pointing to a PDF.

When submitted, the UI sends the URL using the `url` field.

The UI should perform basic URL validation before submitting the request. Detailed validation of whether the URL actually resolves to a PDF is the responsibility of the API.

### Submission

The request must include:

```text
x_client_id: <client_id>
```

On successful submission, the API returns:

```json
{
  "ingestion_id": "<ingestion job id>"
}
```

The UI should not wait for ingestion to complete. On acceptance, it should add
a document-accepted entry with the returned `ingestion_id` to the Ingestion
Activity log, where subsequent event-stream progress is also displayed.

The submission control should be temporarily disabled while the HTTP submission request itself is in progress.

An API submission failure should be displayed as an error message to the user.

---

# 6. Ingestion Activity

The Ingestion Activity section displays asynchronous ingestion events received from:

```text
GET /api/v1/documents/events
```

The request must include:

```text
x_client_id: <client_id>
```

The endpoint returns an SSE (`text/event-stream`) response.

The empty-activity placeholder should be shown only while the activity log has
no accepted-submission entries or ingestion events.

Each event contains information similar to:

```json
{
  "ingestion_id": "469eca536b654421ac4d01e5ec771857",
  "document_id": "469eca536b654421ac4d01e5ec771857_www.mha.gov.in_sites_default_files_2022-07_oci-faq.pdf",
  "client_id": "123",
  "status": "in-progress",
  "stage": "url_requested",
  "error": ""
}
```

## 6.1 Event display

Each received event should be added to the top of the ingestion activity log.

The newest event should be first and remain visible at the top of the log.
Older events should remain available below it in a scrollable area with a
bounded height.

Event cards should use compact spacing so more activity is visible at once.

The UI should support multiple ingestion jobs being processed concurrently.

The `ingestion_id` should be displayed so that events belonging to different ingestion jobs can be distinguished.

The user-friendly `stage` value should be the primary message displayed to the user.

The document filename should be displayed when available from the event/document information.

## 6.2 Status presentation

The UI should visually distinguish ingestion status:

| Status        | Presentation        |
| ------------- | ------------------- |
| `in-progress` | Normal/default text |
| `completed`   | Green               |
| `failed`      | Red                 |

For failed events, the `error` field should be displayed in addition to the stage/message.

The UI should not attempt to interpret or modify the API's `stage` message.

## 6.3 Event stream behavior

The UI should establish the ingestion event stream when the Add Documents page is active.

The UI should continue listening for events while the page is active.

If the SSE connection is interrupted, the UI should attempt to reconnect rather than permanently stopping ingestion monitoring.

Because the current event API does not specify event IDs or replay semantics, the UI should treat the event stream as an ephemeral live stream. It is acceptable for events to be lost across a page refresh or a connection interruption.

The UI is **not required to reconstruct historical ingestion activity**.

Refreshing the page may clear the previously displayed ingestion log.

---

# 7. Ask Questions Page

The Ask Questions page provides the RAG query interface.

The page contains three conceptual sections:

1. **Search Settings**
2. **Question Input**
3. **Answer Display**

The application supports one active question/answer interaction at a time.

When the user submits a new question, the previous answer display is cleared.

Conversation history is not required at this stage.

---

# 8. Search Settings

The Search Settings section is displayed above the question input.

The following settings are supported:

### 8.1 Search Type

Allowed values:

```text
hybrid
dense
bm25
```

The UI should present these as a selectable control.

The selected value is sent to the API as:

```json
{
  "search_type": "<selected value>"
}
```

### 8.2 Top K

`top_k` controls the number of retrieved sources/chunks.

The allowed range is:

```text
1–5
```

The UI should provide a suitable numeric/select control.

The selected value is sent as:

```json
{
  "search": {
    "top_k": <value>
  }
}
```

### 8.3 Settings state

Search settings must be maintained as UI state.

They should survive normal Streamlit reruns and page interactions.

Changing a setting should affect subsequent queries but should not modify an answer that has already been generated.

---

# 9. Question Input

The question input section contains a compact multiline question field, about
two lines high, and an **Ask question** button to its right. It does not display
a separate section heading.

The input should use the placeholder:

```text
Ask a question!
```

When the user selects **Ask question**:

1. Validate that the question is not empty.
2. Clear the current answer display.
3. Submit the query to:

```text
POST /api/v1/query/stream
```

The request body should have the following structure:

```json
{
  "query": "<question>",
  "search_type": "<search type>",
  "search": {
    "top_k": 1
  }
}
```

The actual `top_k` value comes from the current Search Settings.

The `client_id` should also be supplied using the `x_client_id` header if required by the API contract.

The Ask control should not allow another query to be submitted while the current query is actively streaming.

---

# 10. Streaming Answer

The query endpoint returns:

```text
Content-Type: text/event-stream
```

The stream consists of:

* zero or more `answer_delta` events
* one final `completed` event

An `answer_delta` event has the form:

```text
event: answer_delta
data: {"text": "answer chunk text.."}
```

The UI should display the answer incrementally as these events arrive.

The user should therefore see the answer being generated rather than waiting for the entire response.

---

# 11. Answer Display

The Answer Display section uses two vertical columns.

### Left column

The left column contains:

1. The submitted question
2. The generated answer

The question is displayed above the answer and should be visually styled as a user chat message/bubble.

The question bubble should be right-aligned and use theme-aware colors so it
remains distinguishable in both light and dark themes.

The answer should be left-aligned and displayed below the question.

### Right column

The right column displays the detailed sources supporting the answer.

The right column is populated once the final `completed` event is received.

---

# 12. Incremental Answer Rendering

While `answer_delta` events are being received:

1. The text from each event is appended to the current streamed answer.
2. The accumulated answer is rendered in the answer area.
3. Citation links are not required during this phase because citation information is only available in the final `completed` event.

The UI should therefore initially display a plain streaming answer.

When the `completed` event arrives, the UI replaces/refines the streamed answer with the structured answer representation containing inline citations.

The final structured answer is authoritative.

---

# 13. Completed Response

The final event has the following conceptual structure:

```json
{
  "answer": [
    {
      "text": "answer block 1",
      "citations": [
        {
          "source_id": 1
        },
        {
          "source_id": 2
        }
      ]
    },
    {
      "text": "answer block 2",
      "citations": [
        {
          "source_id": 1
        }
      ]
    }
  ],
  "sources": [
    {
      "id": 1,
      "chunk_id": "<doc_id><section_id>_chunk_0",
      "document_id": "<doc_id>",
      "text": "retrieved source text...",
      "section_title": "PDF section title",
      "file_name": "PDF file name",
      "original_file_name": "Original uploaded file name",
      "file_title": "PDF title",
      "file_author": "PDF author",
      "chunk_start_page_idx": 5,
      "chunk_end_page_idx": 6
    }
  ]
}
```

The complete answer displayed to the user is the concatenation of the `text` values from the answer blocks.

An answer block may contain no citations. This is valid and should not be treated as an error.

For example, punctuation-only or transitional blocks may legitimately have an empty citation list.

---

# 14. Inline Citations

Once the `completed` event is received, the UI should render citations inline with the corresponding answer blocks.

A citation link is placed immediately after the answer block to which it refers.

Answer block text should retain normal Markdown formatting such as headings,
lists, and emphasis. For example:

```text
The OCI eligibility criteria require ... (source icon) OCI_faq.pdf+1
```

The citation should appear inline as a compact, light-neutral label with a small
source icon. Its foreground and background should adapt to the active theme.

## 14.1 Citation label

The citation label is derived from the sources referenced by the answer block.

For a citation containing one source:

```text
OCI_faq.pdf
```

For a citation containing multiple sources:

```text
OCI_faq.pdf+2
```

The first source's `original_file_name` is displayed. If it is absent, the UI
falls back to `file_name`.

`+N` represents the number of additional sources referenced by that answer block.

For example:

```text
citations = [1, 4, 7]
```

should display:

```text
OCI_faq.pdf+2
```

The ordering of source IDs should follow the order supplied by the API.

---

# 15. Citation Details

Hovering over or focusing an inline citation should display a theme-aware
popover. Its navigation bar shows previous/next source controls and the current
position on the left, with an icon and total source count on the right. Below
the bar, show only the currently selected source's details: file name, optional
document title and page range, and a normalized preview of its source text.

Do not show author or section names in the citation popover or sources panel.

The complete source text shown in the citation overlay should be rendered as
CommonMark Markdown. Long content should remain scrollable within the popover
rather than being truncated mid-Markdown. The popover should use a fixed,
viewport-aware height capped at 24rem, consistent when switching between
sources; its scrollbar handles different source lengths. Embedded raw HTML
should be displayed as text.

Source Markdown structure should be preserved so that paragraphs and lists
render correctly.

If page information is unavailable, the page range should similarly be omitted.

The overlay is informational only.

Clicking the citation does not currently open the source document or perform any other action.

---

# 16. Sources Panel

The right-hand column of the Answer Display section shows all sources included in the final API response.

Sources should be displayed in the order supplied by the API.

Each source should contain:

* File name
* PDF page range
* Source text

Each source should appear in its own theme-aware card, with the file name and page
range in the header and the remaining metadata and source text clearly separated.
Source text in both cards and citation previews is rendered as CommonMark
Markdown, including pipe tables and their alignment; embedded raw HTML is
displayed as text.

The visual format should be consistent with the information shown in citation overlays.

For example:

```text
OCI_faq.pdf
p. 3–4
Full retrieved source text...
```

The source panel is intended to provide enough context for the user to understand why a source supports the generated answer.

### Source interaction

For the current version:

* Sources are informational only.
* Clicking a source has no action.
* Opening the original PDF is not required.
* Highlighting the cited text inside the original PDF is not required.

These capabilities may be added in a future version.

---

# 17. Error Handling

The UI should handle failures gracefully.

## 17.1 Document submission failure

If `POST /api/v1/documents` returns an error:

* Display an error message.
* Do not add a fabricated ingestion event.
* Allow the user to retry.

## 17.2 Query submission failure

If the query endpoint cannot be established or returns an HTTP error:

* Display an error message in the answer area.
* Do not display stale results from the previous query.
* Allow the user to submit another question.

## 17.3 Query stream failure

If the SSE connection terminates before the `completed` event:

* Preserve the streamed text received so far.
* Indicate that the answer could not be completed.
* Display an appropriate error message.
* Do not attempt to construct citation information from incomplete data.

## 17.4 Invalid completed response

If the `completed` event cannot be parsed or does not conform to the expected response structure:

* Preserve the streamed answer text where possible.
* Display an error indicating that the final structured response could not be processed.
* Do not display incomplete or misleading citations.

---

# 18. Empty Results

The UI should handle the following valid situations:

### No sources

If the completed response contains no sources:

* Display the answer normally.
* Do not display an empty Sources panel.

### Answer with no citations

If the answer contains blocks without citations:

* Display those blocks normally.
* Do not add a citation link after them.

### Empty answer

If the API returns an empty answer:

* Display an appropriate empty-result message rather than leaving the answer area ambiguous.

The UI should not infer that an empty answer means the ingestion or retrieval system failed unless the API explicitly reports an error.

---

# 19. State Management

The UI should maintain the following state independently:

### Client state

* `client_id`

Persistent across browser refreshes through local storage.

### Search state

* `search_type`
* `top_k`

Persistent for the current application/client session.

### Query state

* Current question
* Currently streamed answer
* Final structured answer
* Sources

Query state is replaced when a new question is submitted.

### Ingestion state

* Currently displayed ingestion events

Ingestion events are ephemeral UI state and may be lost after page refresh.

---

# 20. Page Navigation

Switching between **Add Documents** and **Ask Questions** should not generate a new `client_id`.

Search settings should also remain unchanged when navigating between pages.

The ingestion event log may continue to receive events only while the Add Documents page is active. Historical events do not need to be recovered when the user returns to the page.

The application does not need to maintain a complete cross-page event history in this version.

---

# 21. UI/UX Principles

The UI should remain deliberately simple.

It should prioritize:

* Clear document submission
* Visible ingestion progress
* Fast feedback during question answering
* Readable streamed answers
* Clear inline citations
* Easy access to source context

The UI should not attempt to reproduce advanced Perplexity features such as:

* Conversation history
* Follow-up questions
* Suggested questions
* Web search
* Multiple search providers
* Source opening/navigation
* Authentication/accounts
* Sharing conversations
* File collections
* Advanced model selection
* Complex workspace/project management

These can be considered future enhancements.

---

# 22. API/UI Contract Assumptions

The following assumptions are made by the UI:

1. `POST /api/v1/documents` returns an `ingestion_id` when the ingestion job has been accepted.
2. Ingestion processing is asynchronous.
3. `/api/v1/documents/events` emits events associated with the client's `client_id`.
4. Ingestion events are ordered by the event stream.
5. The `completed` query event contains the authoritative final answer and source information.
6. Source IDs referenced by `answer[].citations[].source_id` correspond to IDs in the `sources` array.
7. Source IDs are unique within a query response.
8. Answer block order represents the intended answer order.
9. Concatenating the answer block text produces the complete answer.
10. An answer block may legitimately contain zero citations.
11. Page indexes supplied by the API are converted into user-facing PDF page numbers by the UI according to the API's page-index convention.
12. The API provides source metadata where available and the UI does not attempt to derive missing metadata from the PDF itself.

---

# 23. Out of Scope

The following are explicitly out of scope for the initial implementation:

* Authentication and user accounts
* Persistent conversation history
* Multiple conversations
* Conversation renaming/deletion
* Opening source PDFs
* PDF text highlighting
* Source document preview
* Document deletion
* Document management/search
* Editing document metadata
* Citation verification
* Regenerating answers
* Model selection
* Advanced search configuration
* Ingestion history persistence
* Recovery of missed ingestion events
* Server-side session management
* Mobile-specific UI optimization

The initial implementation should establish the basic end-to-end interaction:

```text
PDF / URL
    ↓
Add Documents
    ↓
RAG API
    ↓
Asynchronous ingestion
    ↓
Ingestion event stream
    ↓
UI ingestion log


Question
    ↓
Ask Questions
    ↓
RAG API
    ↓
Streaming answer
    ↓
Final answer + citations + sources
    ↓
Answer + inline citations + source panel
```
