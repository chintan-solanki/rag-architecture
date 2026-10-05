import unittest

from api.src.helpers.citationprocessor import CitationProcessor
from api.src.helpers.citations import answer_parts
from api.src.services.generation import GenerationService


class CitationProcessorTests(unittest.TestCase):
    def test_generation_prompt_uses_numeric_source_ids(self) -> None:
        prompt = GenerationService.prompt("question", "[Source 1]\nsource text")

        self.assertIn("`[[cite]][1,3,7]`", prompt)
        self.assertIn("do not prefix IDs with `s`", prompt)
        self.assertNotIn("[[cite]][s1", prompt)

    def test_prompt_style_citation_is_converted_to_structured_answer(self) -> None:
        processor = CitationProcessor()
        for chunk in ("Supported claim. ", "[[cite]][1,2]"):
            processor.add_chunk(chunk)
        processor.end_src_stream()

        answer = answer_parts(processor.target_text, processor.all_citations, 2)

        self.assertEqual(
            [part.model_dump() for part in answer],
            [{"text": "Supported claim.", "citations": [{"source_id": 1}, {"source_id": 2}]}],
        )

    def test_trailing_punctuation_and_whitespace_preserve_following_citations(self) -> None:
        processor = CitationProcessor()
        for chunk in (
            "Claim[[cite]][1]",
            "); Next ",
            "[[cite]][2]?",
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


if __name__ == "__main__":
    unittest.main()
