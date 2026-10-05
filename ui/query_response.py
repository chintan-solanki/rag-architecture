from __future__ import annotations

from typing import Any


class ResponseValidationError(ValueError):
    pass


def validate_query_response(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ResponseValidationError("The completed response must be a JSON object.")

    answer = payload.get("answer")
    sources = payload.get("sources")
    if not isinstance(answer, list) or not isinstance(sources, list):
        raise ResponseValidationError(
            "The completed response must contain answer and sources lists."
        )

    source_ids: set[int] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ResponseValidationError("A source entry is not an object.")
        source_id = source.get("id")
        if not _is_positive_int(source_id) or source_id in source_ids:
            raise ResponseValidationError("Source IDs must be unique positive integers.")
        source_ids.add(source_id)
        if not isinstance(source.get("text"), str):
            raise ResponseValidationError("Each source must contain text.")
        for optional_text in (
            "chunk_id",
            "document_id",
            "section_title",
            "file_name",
            "original_file_name",
            "file_title",
            "file_author",
        ):
            value = source.get(optional_text)
            if value is not None and not isinstance(value, str):
                raise ResponseValidationError(
                    f"Source field {optional_text!r} must be text or null."
                )
        for page_index in ("chunk_start_page_idx", "chunk_end_page_idx"):
            value = source.get(page_index)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise ResponseValidationError(
                    f"Source field {page_index!r} must be a non-negative integer or null."
                )
        start_page = source.get("chunk_start_page_idx")
        end_page = source.get("chunk_end_page_idx")
        if start_page is not None and end_page is not None and end_page < start_page:
            raise ResponseValidationError("A source page range is reversed.")

    for part in answer:
        if not isinstance(part, dict) or not isinstance(part.get("text"), str):
            raise ResponseValidationError("Each answer block must contain text.")
        citations = part.get("citations")
        if not isinstance(citations, list):
            raise ResponseValidationError(
                "Each answer block must contain a citations list."
            )
        for citation in citations:
            if not isinstance(citation, dict):
                raise ResponseValidationError("A citation entry is not an object.")
            source_id = citation.get("source_id")
            if not _is_positive_int(source_id) or source_id not in source_ids:
                raise ResponseValidationError(
                    "An answer citation refers to an unknown source ID."
                )

    return payload


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0
