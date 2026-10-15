import unittest

from api.src.helpers.citationprocessor import CitationProcessor
from api.src.helpers.citations import answer_parts
from api.src.services.generation import GenerationService


class CitationProcessorTests(unittest.TestCase):
    def test_generation_prompt_uses_numeric_source_ids(self) -> None:
        prompt = GenerationService.prompt("question", "[Source 1]\nsource text")
        normalized_prompt = " ".join(prompt.split())

        self.assertIn("`[[source]][1,3,7]`", prompt)
        self.assertIn("Answer each question independently", prompt)
        self.assertIn("standalone citation block `[[source]][0]`", prompt)
        self.assertIn("Use the exact literal marker `[[source]]`", prompt)
        self.assertIn("Do not replace `source` with another", prompt)
        self.assertIn("`The source supports this claim. [[source]][7]`", prompt)
        self.assertIn("sentence-ending punctuation (`.`, `?`, or `!`)", normalized_prompt)
        self.assertIn("each block on a new line", normalized_prompt)
        self.assertIn("Put the line break after the citation block", normalized_prompt)
        self.assertIn("Use `0` only for this abstention marker", prompt)
        self.assertIn("do not prefix IDs with `s`", prompt)
        self.assertNotIn("[[source]][s1", prompt)

    def test_prompt_style_citation_is_converted_to_structured_answer(self) -> None:
        processor = CitationProcessor()
        for chunk in ("Supported claim. ", "[[source]][1,2]"):
            processor.add_chunk(chunk)
        processor.end_src_stream()

        answer = answer_parts(processor.target_text, processor.all_citations, 2)

        self.assertEqual(
            [part.model_dump() for part in answer],
            [{"text": "Supported claim.", "citations": [{"source_id": 1}, {"source_id": 2}]}],
        )

    def test_null_source_marker_preserves_abstention_beside_cited_answer(self) -> None:
        processor = CitationProcessor()
        for chunk in (
            "The source supports this answer.",
            "[[source]][1] ",
            "I cannot answer the other question from the provided sources.",
            "[[source]][0]",
        ):
            processor.add_chunk(chunk)
        processor.end_src_stream()

        answer = answer_parts(processor.target_text, processor.all_citations, 1)

        self.assertEqual(
            [part.model_dump() for part in answer],
            [
                {
                    "text": "The source supports this answer. ",
                    "citations": [{"source_id": 1}],
                },
                {
                    "text": "I cannot answer the other question from the provided sources.",
                    "citations": [],
                },
            ],
        )

    def test_trailing_punctuation_and_whitespace_preserve_following_citations(self) -> None:
        processor = CitationProcessor()
        for chunk in (
            "Claim[[source]][1]",
            "); Next ",
            "[[source]][2]?",
            " More.",
        ):
            processor.add_chunk(chunk)
        processor.end_src_stream()

        answer = answer_parts(processor.target_text, processor.all_citations, 2)

        self.assertEqual(
            processor.target_text,
            "Claim); Next? More.",
        )
        self.assertEqual(
            [part.model_dump() for part in answer],
            [
                {"text": "Claim); ", "citations": [{"source_id": 1}]},
                {"text": "Next? ", "citations": [{"source_id": 2}]},
                {"text": "More.", "citations": []},
            ],
        )

    def test_new_answer_block_after_citation_starts_on_new_line(self) -> None:
        processor = CitationProcessor()
        for chunk in (
            "1. First point.",
            "[[source]][1]",
            "\n2. Second point.",
            "[[source]][2]",
        ):
            processor.add_chunk(chunk)
        processor.end_src_stream()

        answer = answer_parts(processor.target_text, processor.all_citations, 2)

        self.assertEqual(processor.target_text, "1. First point.\n2. Second point.")
        self.assertEqual(
            [part.model_dump() for part in answer],
            [
                {
                    "text": "1. First point.",
                    "citations": [{"source_id": 1}],
                },
                {
                    "text": "\n2. Second point.",
                    "citations": [{"source_id": 2}],
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
