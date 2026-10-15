from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common" / "src"))

from common.models.ingestionconfig import ChunkHeaderType, IngestionConfig
from helpers.contextretrieval.chunkcontextretriever import ChunkContextRetriever
from helpers.contextretrieval.chunkcontextualizedsummarygenerator import (
    ChunkContextualizedSummaryGenerator,
)
from models.ingestion import IndexChunk, IndexDocument

LLM_CONFIG = {
    "provider": "openai",
    "model": "test-model",
    "api_key_env": "OPENAI_API_KEY",
}


class FakeLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> SimpleNamespace:
        self.prompts.append(prompt)
        return SimpleNamespace(text=self.response)


class ChunkContextRetrievalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.chunk = IndexChunk(chunk_id="chunk-1", text="Chunk content.")
        self.document = IndexDocument(
            doc_id="doc-1",
            text="# Section title\nFull section content.",
            metadata={"section_title": "Section title"},
        )

    def test_contextualized_summary_uses_containing_section_and_chunk(self) -> None:
        llm = FakeLLM("Details from the section.")
        generator = ChunkContextualizedSummaryGenerator(
            llm_config=LLM_CONFIG,
            llm=llm,
        )

        summary = generator.get_summary(self.chunk, self.document)

        self.assertEqual(summary, "summary: Details from the section.")
        self.assertIn(self.document.text, llm.prompts[0])
        self.assertIn(self.chunk.text, llm.prompts[0])

    def test_contextualized_summary_builds_llm_from_provider_config(self) -> None:
        llm = FakeLLM("Details from the section.")
        generator = ChunkContextualizedSummaryGenerator(llm_config=LLM_CONFIG)

        with patch(
            "helpers.contextretrieval.chunkcontextualizedsummarygenerator.create_llm",
            return_value=llm,
        ) as create_llm:
            header = generator.get_context_header(self.chunk, self.document)

        create_llm.assert_called_once_with(LLM_CONFIG)
        self.assertEqual(header.summary, "Details from the section.")

    def test_metadata_header_appends_comment(self) -> None:
        retriever = ChunkContextRetriever(
            IngestionConfig(
                chunk_header_type=ChunkHeaderType.file_metadata,
                comment="  Focus on the results. ",
            ),
            {"file_name": "report.pdf"},
            LLM_CONFIG,
        )

        header = retriever.get_chunk_context(self.chunk, self.document)

        self.assertEqual(
            header,
            "<context>\n"
            "Document name: report.pdf\n"
            "Section title: Section title\n"
            "comment: Focus on the results.\n"
            "</context>",
        )

    def test_contextualized_header_appends_comment(self) -> None:
        retriever = ChunkContextRetriever(
            IngestionConfig(
                chunk_header_type=ChunkHeaderType.contextualized_chunk_summary,
                comment="Additional user context.",
            ),
            {},
            LLM_CONFIG,
        )
        fake_llm = FakeLLM("This chunk describes the section.")
        retriever.summary_generator._llm = fake_llm

        header = retriever.get_chunk_context(self.chunk, self.document)

        self.assertEqual(
            header,
            "<context>\n"
            "summary: This chunk describes the section.\n"
            "comment: Additional user context.\n"
            "</context>",
        )

    def test_empty_comment_is_skipped(self) -> None:
        for comment in (None, "", " \n "):
            with self.subTest(comment=comment):
                retriever = ChunkContextRetriever(
                    IngestionConfig(
                        chunk_header_type=ChunkHeaderType.file_metadata,
                        comment=comment,
                    ),
                    {},
                    LLM_CONFIG,
                )

                self.assertEqual(
                    retriever.get_chunk_context(self.chunk, self.document),
                    "<context>\nSection title: Section title\n</context>",
                )

    def test_blank_llm_response_fails_explicitly(self) -> None:
        generator = ChunkContextualizedSummaryGenerator(
            llm_config=LLM_CONFIG,
            llm=FakeLLM(" \n "),
        )

        with self.assertRaisesRegex(RuntimeError, "empty contextualized chunk summary"):
            generator.get_summary(self.chunk, self.document)


if __name__ == "__main__":
    unittest.main()
