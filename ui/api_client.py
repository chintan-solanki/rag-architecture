from __future__ import annotations

from collections.abc import Iterator
import http.client
import json
from pathlib import PurePath
import urllib.error
import urllib.parse
import urllib.request
import uuid

from ui.sse import SSEEvent, iter_sse_events


class ApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class RagApiClient:
    def __init__(self, base_url: str, *, timeout: float = 120.0) -> None:
        self.base_url = f"{base_url.rstrip('/')}/api/v1"
        self.timeout = timeout

    def submit_upload(
        self, *, client_id: str, filename: str, content: bytes, content_type: str
    ) -> str:
        boundary = f"----rag-ui-{uuid.uuid4().hex}"
        safe_filename = PurePath(filename).name.replace("\r", "").replace("\n", "")
        safe_filename = safe_filename.replace("\\", "\\\\").replace('"', '\\"')
        body = b"".join(
            (
                f"--{boundary}\r\n".encode(),
                (
                    'Content-Disposition: form-data; name="file"; '
                    f'filename="{safe_filename}"\r\n'
                ).encode(),
                f"Content-Type: {content_type}\r\n\r\n".encode(),
                content,
                f"\r\n--{boundary}--\r\n".encode(),
            )
        )
        request = urllib.request.Request(
            f"{self.base_url}/documents",
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                **self._client_headers(client_id),
            },
            method="POST",
        )
        return self._submit_document(request)

    def submit_url(self, *, client_id: str, url: str) -> str:
        body = urllib.parse.urlencode({"url": url}).encode()
        request = urllib.request.Request(
            f"{self.base_url}/documents",
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                **self._client_headers(client_id),
            },
            method="POST",
        )
        return self._submit_document(request)

    def _submit_document(self, request: urllib.request.Request) -> str:
        payload = self._read_json_response(request)
        ingestion_id = payload.get("ingestion_id") if isinstance(payload, dict) else None
        if not isinstance(ingestion_id, str) or not ingestion_id.strip():
            raise ApiError("The API accepted no valid ingestion ID in its response.")
        return ingestion_id

    def open_ingestion_events(self, client_id: str) -> http.client.HTTPResponse:
        query = urllib.parse.urlencode({"x_client_id": client_id})
        request = urllib.request.Request(
            f"{self.base_url}/documents/events?{query}",
            headers={
                "Accept": "text/event-stream",
                "Cache-Control": "no-cache",
                **self._client_headers(client_id),
            },
            method="GET",
        )
        return self._open_stream(request)

    @staticmethod
    def _client_headers(client_id: str) -> dict[str, str]:
        # Send both spellings: the API header parameter normalizes underscores to hyphens.
        return {"x_client_id": client_id, "x-client-id": client_id}

    def iter_query_events(
        self,
        *,
        client_id: str,
        query: str,
        search_type: str,
        top_k: int,
    ) -> Iterator[SSEEvent]:
        body = json.dumps(
            {
                "query": query,
                "search_type": search_type,
                "search": {"top_k": top_k},
            }
        ).encode()
        request = urllib.request.Request(
            f"{self.base_url}/query/stream",
            data=body,
            headers={
                "Accept": "text/event-stream",
                "Content-Type": "application/json",
                **self._client_headers(client_id),
            },
            method="POST",
        )
        response = self._open_stream(request)
        try:
            yield from iter_sse_events(response)
        finally:
            response.close()

    def _read_json_response(self, request: urllib.request.Request) -> object:
        response = self._open_stream(request)
        try:
            try:
                raw_body = response.read()
            except (http.client.HTTPException, OSError, TimeoutError) as exc:
                raise ApiError(f"Could not read the RAG API response: {exc}") from exc
        finally:
            response.close()
        try:
            return json.loads(raw_body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ApiError("The API returned an invalid JSON response.") from exc

    def _open_stream(
        self, request: urllib.request.Request
    ) -> http.client.HTTPResponse:
        try:
            response = urllib.request.urlopen(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            detail = self._http_error_detail(exc)
            exc.close()
            raise ApiError(detail, status_code=exc.code) from exc
        except (
            http.client.HTTPException,
            urllib.error.URLError,
            TimeoutError,
            OSError,
        ) as exc:
            raise ApiError(f"Could not connect to the RAG API: {exc}") from exc

        if request.get_method() in {"GET", "POST"} and request.headers.get(
            "Accept"
        ) == "text/event-stream":
            content_type = response.headers.get("Content-Type", "").lower()
            if "text/event-stream" not in content_type:
                response.close()
                raise ApiError("The API did not return an event stream.")
        return response

    @staticmethod
    def _http_error_detail(error: urllib.error.HTTPError) -> str:
        try:
            body = error.read().decode("utf-8", errors="replace")
        except OSError:
            body = ""
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            detail = parsed.get("detail")
            if isinstance(detail, str) and detail:
                return f"RAG API returned HTTP {error.code}: {detail}"
        if body:
            return f"RAG API returned HTTP {error.code}: {body[:500]}"
        return f"RAG API returned HTTP {error.code}."
