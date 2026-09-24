from collections.abc import Iterable
from ..models.query import AnswerPart, Citation


def answer_parts(text: str, ranges: Iterable[tuple[int, int, list[int]]], source_count: int) -> list[AnswerPart]:
    """Turn CitationProcessor ranges into validated, citation-free answer parts."""
    result: list[AnswerPart] = []
    cursor = 0
    for start, end, ids in ranges:
        start = max(0, min(start, len(text)))
        end = max(start, min(end, len(text)))
        if start > cursor:
            result.append(AnswerPart(text=text[cursor:start]))
        valid = []
        for source_id in ids:
            if 1 <= source_id <= source_count and source_id not in valid:
                valid.append(source_id)
        if end > start or valid:
            result.append(AnswerPart(text=text[start:end], citations=[Citation(source_id=i) for i in valid]))
        cursor = max(cursor, end)
    if cursor < len(text):
        result.append(AnswerPart(text=text[cursor:]))
    return [part for part in result if part.text or part.citations]
