import unittest

from ui.components.citations import (
    citation_label,
    citation_source_details,
    format_page_range,
    render_answer_html,
    source_card_html,
)
from ui.query_response import ResponseValidationError, validate_query_response


def source(
    source_id: int,
    *,
    filename: str | None = "guide.pdf",
    text: str = "  Line one\n\n   line two and more text. ",
    start: int | None = 2,
    end: int | None = 3,
) -> dict:
    return {
        "id": source_id,
        "text": text,
        "file_name": filename,
        "original_file_name": None,
        "section_title": "Section",
        "file_author": None,
        "chunk_start_page_idx": start,
        "chunk_end_page_idx": end,
    }


class CitationRenderingTests(unittest.TestCase):
    def test_labels_preserve_api_order_and_count_additional_sources(self) -> None:
        sources = {1: source(1), 4: source(4, filename="other.pdf")}

        self.assertEqual(citation_label([{"source_id": 4}], sources), "other.pdf")
        self.assertEqual(
            citation_label([{"source_id": 1}, {"source_id": 4}], sources),
            "guide.pdf+1",
        )

    def test_original_file_name_is_used_for_labels_and_source_details(self) -> None:
        item = source(1, filename="stored-name.pdf")
        item["original_file_name"] = "uploaded-name.pdf"

        self.assertEqual(
            citation_label([{"source_id": 1}], {1: item}),
            "uploaded-name.pdf",
        )
        self.assertIn("uploaded-name.pdf", source_card_html(item))
        self.assertEqual(citation_source_details(item)[0], "uploaded-name.pdf")

    def test_sigmoid_relevance_score_is_shown_in_source_and_inline_cards(self) -> None:
        item = source(1)
        item["relevance_score"] = 0.876
        answer = [{"text": "Claim.", "citations": [{"source_id": 1}]}]

        source_card = source_card_html(item)
        citation_card = render_answer_html(answer, [item])

        for rendered in (source_card, citation_card):
            self.assertIn("Relevance 0.88", rendered)
            self.assertIn("not a probability or confidence estimate", rendered)

    def test_page_ranges_convert_zero_based_indices_to_pdf_pages(self) -> None:
        self.assertEqual(format_page_range(2, 3), "p. 3–4")
        self.assertEqual(format_page_range(2, 2), "p. 3")
        self.assertEqual(format_page_range(None, 2), "p. 3")
        self.assertIsNone(format_page_range(None, None))

    def test_hover_details_normalize_and_truncate_source_text(self) -> None:
        item = source(1, text="a " * 80)
        item["file_author"] = "Author"
        details = citation_source_details(item)

        self.assertIn("p. 3–4", details)
        self.assertNotIn("Section", details)
        self.assertNotIn("Author", details)
        self.assertTrue(details[-1].endswith("…"))
        self.assertNotIn("\n", details[-1])

    def test_citation_preview_preserves_markdown_line_structure(self) -> None:
        details = citation_source_details(
            source(1, text="**Heading**\n\n- First item\n- Second item"),
            preview_limit=None,
        )
        rendered = render_answer_html(
            [{"text": "Claim.", "citations": [{"source_id": 1}]}],
            [source(1, text="**Heading**\n\n- First item\n- Second item")],
        )

        self.assertIn("**Heading**\n\n- First item\n- Second item", details[-1])
        self.assertIn("<strong>Heading</strong>", rendered)
        self.assertIn("<ul>", rendered)

    def test_citation_popover_renders_full_markdown_source_without_cutting_syntax(self) -> None:
        long_prefix = "First sentence. " * 12
        source_text = f"{long_prefix}**complete bold text** and more content after it."
        rendered = render_answer_html(
            [{"text": "Claim.", "citations": [{"source_id": 1}]}],
            [source(1, text=source_text)],
        )

        self.assertIn("<strong>complete bold text</strong>", rendered)
        self.assertIn("and more content after it.", rendered)
        self.assertNotIn("…", rendered)

    def test_inline_citation_has_navigable_theme_aware_source_popover(self) -> None:
        answer = [
            {
                "text": "Claim.",
                "citations": [{"source_id": 1}, {"source_id": 4}],
            }
        ]
        first = source(1, text="First source text.")
        first["file_title"] = "First guide"
        second = source(4, filename="other.pdf", text="Second source text.")

        rendered = render_answer_html(answer, [first, second])

        self.assertIn('id="citation-0-0"', rendered)
        self.assertIn('id="citation-0-1"', rendered)
        self.assertIn('for="citation-0-1"', rendered)
        self.assertIn('for="citation-0-0"', rendered)
        self.assertIn("1/2", rendered)
        self.assertIn("2/2", rendered)
        self.assertIn("2 sources", rendered)
        self.assertIn("First guide", rendered)
        self.assertIn("Second source text.", rendered)
        self.assertIn("var(--background-color", rendered)
        self.assertIn("var(--text-color", rendered)
        self.assertIn('role="group" aria-label="Citation sources"', rendered)
        self.assertIn("height:min(45vh,24rem)", rendered)
        self.assertIn("overflow-y:auto", rendered)
        self.assertIn("position:sticky", rendered)
        self.assertIn("visibility 0s linear .2s", rendered)
        self.assertNotIn('href="#', rendered)
        self.assertNotIn('title="', rendered)
        self.assertNotIn("Section", rendered)

    def test_citation_count_suffix_is_inside_bubble_but_not_link_target(self) -> None:
        rendered = render_answer_html(
            [
                {
                    "text": "Claim.",
                    "citations": [{"source_id": 1}, {"source_id": 4}],
                }
            ],
            [source(1), source(4, filename="other.pdf")],
        )

        trigger = rendered.split('class="citation-trigger"', 1)[1].split(
            '</span><div class="citation-popover"', 1
        )[0]
        self.assertIn("guide.pdf", trigger)
        self.assertIn('<span class="citation-suffix">+1</span>', trigger)
        self.assertIn('aria-label="guide.pdf"', trigger)
        self.assertNotIn('href="', trigger)
        self.assertNotIn('href="#', rendered)

    def test_source_text_markdown_is_rendered_without_enabling_raw_html(self) -> None:
        item = source(
            1,
            text="**Important** and *emphasized*.\n\n- First item\n- Second item\n\n<script>alert(1)</script>",
        )
        rendered_card = source_card_html(item)
        rendered_citation = render_answer_html(
            [{"text": "Claim.", "citations": [{"source_id": 1}]}],
            [item],
        )

        self.assertIn("<strong>Important</strong>", rendered_card)
        self.assertIn("<em>emphasized</em>", rendered_card)
        self.assertIn("<ul>", rendered_card)
        self.assertIn("&lt;script&gt;", rendered_card)
        self.assertNotIn("<script>", rendered_card)
        self.assertIn("<strong>Important</strong>", rendered_citation)
        self.assertIn("<ul>", rendered_citation)
        self.assertIn("&lt;script&gt;", rendered_citation)
        self.assertNotIn("<script>", rendered_citation)

    def test_pipe_tables_render_as_markdown_tables_in_source_views(self) -> None:
        table = (
            "| LLM | Accuracy | Precision |\n"
            "| --- | ---: | ---: |\n"
            "| GPT-3.5 | 72.7% | 75.8% |\n"
            "| RAG | **88.5%** | **91.4%** |"
        )
        item = source(1, text=table)

        source_card = source_card_html(item)
        citation_popover = render_answer_html(
            [{"text": "Claim.", "citations": [{"source_id": 1}]}],
            [item],
        )

        for rendered in (source_card, citation_popover):
            self.assertIn("<table>", rendered)
            self.assertIn("<th>LLM</th>", rendered)
            self.assertIn("<td>GPT-3.5</td>", rendered)
            self.assertIn("<strong>88.5%</strong>", rendered)
            self.assertIn('style="text-align:right"', rendered)
            self.assertIn("overflow-x:auto", rendered)

    def test_source_headings_are_smaller(self) -> None:
        item = source(1, text="# Large source heading")
        card = source_card_html(item)
        citation = render_answer_html(
            [{"text": "Claim.", "citations": [{"source_id": 1}]}],
            [item],
        )

        self.assertIn("font-size:1.15rem!important", card)
        self.assertIn("font-size:1rem!important", citation)

    def test_answer_html_escapes_text_and_renders_citation_label(self) -> None:
        answer = [
            {
                "text": "<unsafe> # **literal**",
                "citations": [{"source_id": 1}],
            }
        ]

        rendered = render_answer_html(answer, [source(1)])

        self.assertIn("&lt;unsafe&gt;", rendered)
        self.assertIn("# <strong>literal</strong>", rendered)
        self.assertIn("guide.pdf", rendered)
        self.assertIn('aria-label="guide.pdf"', rendered)
        self.assertIn("<svg", rendered)
        self.assertIn("background:var(--secondary-background-color", rendered)
        self.assertNotIn("<unsafe>", rendered)

    def test_xml_source_content_stays_inside_the_citation_popover(self) -> None:
        source_text = (
            "<ChunkContext><summary>Context summary</summary></ChunkContext>\n"
            "# 1. Who is eligible to apply?\n\n"
            "A foreign national may apply."
        )

        rendered = render_answer_html(
            [{"text": "Supported answer.", "citations": [{"source_id": 1}]}],
            [source(1, text=source_text)],
        )
        answer_text, citation_popover = rendered.split(
            '<div class="citation-popover"', maxsplit=1
        )

        self.assertNotIn("Who is eligible to apply?", answer_text)
        self.assertIn(
            "&lt;ChunkContext&gt;&lt;summary&gt;Context summary"
            "&lt;/summary&gt;&lt;/ChunkContext&gt;",
            citation_popover,
        )
        self.assertIn("<h1>1. Who is eligible to apply?</h1>", citation_popover)

    def test_uncited_abstention_text_renders_without_a_citation_badge(self) -> None:
        answer = [
            {"text": "Supported claim. ", "citations": [{"source_id": 1}]},
            {
                "text": "I cannot answer the other question from the provided sources.",
                "citations": [],
            },
        ]

        rendered = render_answer_html(answer, [source(1)])

        self.assertIn("Supported claim.", rendered)
        self.assertIn(
            "I cannot answer the other question from the provided sources.",
            rendered,
        )
        self.assertEqual(rendered.count('class="citation-wrap"'), 1)

    def test_source_card_escapes_metadata_and_shows_structured_details(self) -> None:
        item = source(1, filename="<guide>.pdf", text="  First line\n second line ")
        item["file_author"] = "Hidden author"
        rendered = source_card_html(
            item
        )

        self.assertIn("&lt;guide&gt;.pdf", rendered)
        self.assertIn("p. 3–4", rendered)
        self.assertNotIn("Section", rendered)
        self.assertNotIn("Hidden author", rendered)
        self.assertIn("<p>First line\nsecond line</p>", rendered)
        self.assertIn("border-radius:.75rem", rendered)
        self.assertIn("background:var(--secondary-background-color", rendered)
        self.assertNotIn("<guide>", rendered)

    def test_validates_source_references_and_allows_uncited_blocks(self) -> None:
        cited_source = source(1)
        cited_source["original_file_name"] = "uploaded-guide.pdf"
        payload = {
            "answer": [
                {"text": "Opening.", "citations": []},
                {"text": "Claim.", "citations": [{"source_id": 1}]},
            ],
            "sources": [cited_source],
        }

        self.assertIs(validate_query_response(payload), payload)
        payload["answer"][1]["citations"] = [{"source_id": 9}]
        with self.assertRaises(ResponseValidationError):
            validate_query_response(payload)

    def test_rejects_invalid_relevance_score(self) -> None:
        payload = {"answer": [], "sources": [source(1)]}
        payload["sources"][0]["relevance_score"] = 1.1

        with self.assertRaises(ResponseValidationError):
            validate_query_response(payload)

    def test_rejects_reversed_source_page_range(self) -> None:
        payload = {"answer": [], "sources": [source(1, start=4, end=2)]}

        with self.assertRaises(ResponseValidationError):
            validate_query_response(payload)


if __name__ == "__main__":
    unittest.main()
