from __future__ import annotations

import html
import math
import re
from typing import Any

from markdown_it import MarkdownIt


_MARKDOWN = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable(
    "table"
)


def citation_label(
    citations: list[dict[str, Any]], sources_by_id: dict[int, dict[str, Any]]
) -> str:
    first_id = citations[0]["source_id"]
    first_source = sources_by_id[first_id]
    filename = _source_filename(first_source) or f"Source {first_id}"
    suffix = f"+{len(citations) - 1}" if len(citations) > 1 else ""
    return f"{filename}{suffix}"


def render_answer_html(
    answer: list[dict[str, Any]], sources: list[dict[str, Any]]
) -> str:
    sources_by_id = {source["id"]: source for source in sources}
    max_citation_sources = max((len(part["citations"]) for part in answer), default=0)
    fragments = [_citation_styles()] if max_citation_sources else []
    for part_index, part in enumerate(answer):
        inline_text = part["text"].replace("\r\n", "\n").replace("\r", "\n")
        fragments.append(_MARKDOWN.renderInline(inline_text.replace("\n", "  \n")))
        citations = part["citations"]
        if not citations:
            continue
        fragments.append(_citation_popover(citations, sources_by_id, part_index))
    return "".join(fragments)


def _citation_popover(
    citations: list[dict[str, Any]],
    sources_by_id: dict[int, dict[str, Any]],
    citation_index: int,
) -> str:
    source_ids = [item["source_id"] for item in citations]
    count = len(source_ids)
    group_name = f"citation-{citation_index}"
    first_source_name = (
        _source_filename(sources_by_id[source_ids[0]]) or f"Source {source_ids[0]}"
    )
    fragments = ['<div class="citation-wrap">']

    for index in range(count):
        checked = " checked" if index == 0 else ""
        fragments.append(
            f'<input class="citation-state citation-state-{index}" type="radio" '
            f'name="{group_name}" id="{group_name}-{index}" '
            f'aria-label="Show source {index + 1} of {count}"{checked}>'
        )

    fragments.extend(
        (
            f'<span class="citation-trigger" tabindex="0" '
            f'aria-label="{html.escape(first_source_name, quote=True)}">',
            _source_icon(),
            f"{html.escape(first_source_name)}",
            (
                f'<span class="citation-suffix">+{count - 1}</span>'
                if count > 1
                else ""
            ),
            "</span>",
            '<div class="citation-popover" role="group" aria-label="Citation sources">',
        )
    )
    for index, source_id in enumerate(source_ids):
        source = sources_by_id[source_id]
        previous = (
            f'<label class="citation-nav-link" for="{group_name}-{index - 1}" '
            'aria-label="Previous source">&lsaquo;</label>'
            if index > 0
            else '<span class="citation-nav-link is-disabled" aria-hidden="true">&lsaquo;</span>'
        )
        following = (
            f'<label class="citation-nav-link" for="{group_name}-{index + 1}" '
            'aria-label="Next source">&rsaquo;</label>'
            if index + 1 < count
            else '<span class="citation-nav-link is-disabled" aria-hidden="true">&rsaquo;</span>'
        )
        fragments.append(
            f'<div class="citation-panel citation-panel-{index}">'
            '<div class="citation-nav">'
            '<div class="citation-nav-controls">'
            f"{previous}<span>{index + 1}/{count}</span>{following}"
            "</div>"
            '<div class="citation-source-count">'
            f"{_source_icon()}{count} {'source' if count == 1 else 'sources'}"
            "</div></div>"
            f"{_citation_source_html(source)}</div>"
        )
    fragments.append("</div></div>")
    return "".join(fragments)


def _citation_source_html(source: dict[str, Any]) -> str:
    source_id = source["id"]
    filename = html.escape(
        _source_filename(source) or source.get("file_title") or f"Source {source_id}"
    )
    title = source.get("file_title")
    page_range = format_page_range(
        source.get("chunk_start_page_idx"), source.get("chunk_end_page_idx")
    )
    source_text = source.get("text", "")
    parts = [
        '<div class="citation-source-details">'
        f'<div class="citation-source-filename">{_source_icon()}{filename}'
        f'{_relevance_score_html(source)}</div>'
    ]
    if title:
        parts.append(f'<strong class="citation-source-title">{html.escape(title)}</strong>')
    if page_range:
        parts.append(f'<div class="citation-source-page">{html.escape(page_range)}</div>')
    parts.append(
        f'<div class="citation-source-text">{_render_markdown(source_text)}</div></div>'
    )
    return "".join(parts)


def _source_icon() -> str:
    return (
        '<svg class="citation-icon" aria-hidden="true" width="16" height="16" '
        'viewBox="0 0 16 16" fill="none">'
        '<path d="M6.4 10.6 9.6 7.4M5.2 12.2l-1.4 1.4a3 3 0 0 1-4.2-4.2l3-3a3 3 0 0 1 4.2 0'
        'm4.2-.4 1.4-1.4a3 3 0 0 1 4.2 4.2l-3 3a3 3 0 0 1-4.2 0" '
        'stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>'
        "</svg>"
    )


def _citation_styles() -> str:
    return f"<style>{_CITATION_STYLES}</style>"


_CITATION_STYLES = """
.citation-wrap{display:inline-block;position:relative;vertical-align:baseline}
.citation-state{position:absolute;width:1px;height:1px;margin:-1px;overflow:hidden;
clip:rect(0,0,0,0);white-space:nowrap}
.citation-trigger{display:inline-flex;align-items:center;gap:.25rem;margin-left:.3rem;
padding:.08rem .4rem;border-radius:.45rem;max-width:18rem;white-space:normal;
overflow-wrap:anywhere;text-align:left;background:var(--secondary-background-color,#f0f2f6);
color:var(--text-color,#31333f);font:.78em/1.35 sans-serif;vertical-align:baseline;cursor:help}
.citation-suffix{font-size:.78em;color:var(--text-color,#31333f);opacity:.72}
.citation-icon{flex:none;width:16px;height:16px;opacity:.72}
.citation-popover{display:block;visibility:hidden;opacity:0;pointer-events:none;
transition:opacity .12s ease,visibility 0s linear .2s;
position:absolute;left:0;bottom:100%;z-index:9999;
box-sizing:border-box;width:min(25rem,calc(100vw - 2rem));height:min(45vh,24rem);
overflow-y:auto;overscroll-behavior:contain;padding:0 .9rem .9rem;
border:1px solid var(--border-color,rgba(128,128,128,.28));border-radius:1rem;
box-shadow:0 .6rem 1.5rem rgba(0,0,0,.18);
background:var(--background-color,var(--secondary-background-color,#fff));
color:var(--text-color,#31333f);font: .9rem/1.45 sans-serif;text-align:left}
.citation-wrap:hover .citation-popover,.citation-wrap:focus-within .citation-popover{
visibility:visible;opacity:1;pointer-events:auto;transition-delay:0s}
.citation-trigger:focus-visible{outline:2px solid var(--primary-color,#ff4b4b)}
.citation-nav{display:flex;align-items:center;justify-content:space-between;gap:1rem;
position:sticky;top:0;z-index:1;min-height:3rem;margin:0 -.9rem .8rem;padding:0 .9rem;
border-bottom:1px solid var(--border-color,rgba(128,128,128,.2));
background:var(--background-color,var(--secondary-background-color,#fff));
color:var(--text-color,#31333f)}
.citation-nav-controls,.citation-source-count{display:inline-flex;align-items:center;gap:.65rem}
.citation-nav-controls{color:var(--text-color,#31333f);opacity:.72}
.citation-nav-link{display:inline-flex;align-items:center;justify-content:center;min-width:1rem;
font-size:1.35rem;line-height:1;cursor:pointer;user-select:none;color:inherit;
text-decoration:none}
.citation-nav-link.is-disabled{opacity:.35}
.citation-source-count{font-size:.85rem;white-space:nowrap}
.citation-source-count .citation-icon{color:var(--primary-color,#ff4b4b)}
.citation-panel{display:none}
.citation-state-0:checked~.citation-popover .citation-panel-0,
.citation-state-1:checked~.citation-popover .citation-panel-1,
.citation-state-2:checked~.citation-popover .citation-panel-2,
.citation-state-3:checked~.citation-popover .citation-panel-3,
.citation-state-4:checked~.citation-popover .citation-panel-4,
.citation-state-5:checked~.citation-popover .citation-panel-5,
.citation-state-6:checked~.citation-popover .citation-panel-6,
.citation-state-7:checked~.citation-popover .citation-panel-7,
.citation-state-8:checked~.citation-popover .citation-panel-8,
.citation-state-9:checked~.citation-popover .citation-panel-9{display:block}
.citation-source-details{display:flex;flex-direction:column;gap:.35rem}
.citation-source-filename{display:flex;align-items:center;gap:.45rem;color:var(--text-color,#31333f);
opacity:.65;font-size:.9rem;overflow-wrap:anywhere}
.citation-source-filename .citation-icon{color:var(--primary-color,#ff4b4b)}
.relevance-score{flex:none;margin-left:auto;padding:.12rem .4rem;border-radius:.45rem;
background:var(--secondary-background-color,#f0f2f6);color:var(--text-color,#31333f);
font-size:.78em;white-space:nowrap}
.citation-source-title{font-weight:600}
.citation-source-page{color:var(--text-color,#31333f);opacity:.65;font-size:.88rem}
.citation-source-text{color:var(--text-color,#31333f);opacity:.68;overflow-wrap:anywhere}
.citation-source-text p{margin:.25rem 0}
.citation-source-text p:first-child{margin-top:0}
.citation-source-text p:last-child{margin-bottom:0}
.citation-source-text table{display:block;width:100%;overflow-x:auto;border-collapse:collapse}
.citation-source-text th,.citation-source-text td{padding:.3rem .45rem;
border:1px solid var(--border-color,rgba(128,128,128,.28))}
.source-markdown table{display:block;width:100%;overflow-x:auto;border-collapse:collapse}
.source-markdown th,.source-markdown td{padding:.3rem .45rem;
border:1px solid var(--border-color,rgba(128,128,128,.28))}
.citation-source-text h1,.citation-source-text h2,.citation-source-text h3,
.citation-source-text h4,.citation-source-text h5,.citation-source-text h6{
font-size:1rem!important;line-height:1.3!important;margin:.3rem 0!important}
.citation-source-text h1,.citation-source-text h2{font-weight:650}
.source-markdown h1,.source-markdown h2,.source-markdown h3,
.source-markdown h4,.source-markdown h5,.source-markdown h6{
font-size:1.15rem!important;line-height:1.3!important;margin:.5rem 0!important}
.source-markdown h1,.source-markdown h2{font-weight:650}
"""


def source_card_html(source: dict[str, Any]) -> str:
    source_id = source["id"]
    filename = (
        _source_filename(source) or source.get("file_title") or f"Source {source_id}"
    )
    page_range = format_page_range(
        source.get("chunk_start_page_idx"), source.get("chunk_end_page_idx")
    )
    text = source.get("text", "")

    details = [
        '<style>.source-markdown p{margin:.35rem 0}'
        '.source-markdown p:first-child{margin-top:0}'
        '.source-markdown p:last-child{margin-bottom:0}'
        '.source-markdown ul,.source-markdown ol{padding-left:1.5rem}'
        '.source-markdown table{display:block;width:100%;overflow-x:auto;border-collapse:collapse}'
        '.source-markdown th,.source-markdown td{padding:.3rem .45rem;'
        'border:1px solid var(--border-color,rgba(128,128,128,.28))}'
        '.source-markdown pre{overflow-x:auto}'
        '.source-markdown h1,.source-markdown h2,.source-markdown h3,'
        '.source-markdown h4,.source-markdown h5,.source-markdown h6{'
        'font-size:1.15rem!important;line-height:1.3!important;margin:.5rem 0!important}'
        '.relevance-score{flex:none;padding:.12rem .4rem;border-radius:.45rem;'
        'background:var(--secondary-background-color,#f0f2f6);'
        'color:var(--text-color,#31333f);font-size:.78em;white-space:nowrap}'
        '.source-markdown h1,.source-markdown h2{font-weight:650}</style>',
        '<article style="box-sizing:border-box;width:100%;margin:0 0 .75rem;'
        'padding:.9rem 1rem;border:1px solid '
        'var(--border-color, rgba(128,128,128,.28));border-radius:.75rem;'
        'box-shadow:0 1px 3px rgba(0,0,0,.08);'
        'background:var(--secondary-background-color, #f0f2f6);'
        'color:var(--text-color, #31333f);overflow-wrap:anywhere">'
        '<header style="display:flex;justify-content:space-between;align-items:flex-start;'
        'gap:.65rem;min-width:0">'
        f'<strong style="min-width:0;flex:1;font-size:.95em;overflow-wrap:anywhere">'
        f"{html.escape(filename)}</strong>"
        f"{_relevance_score_html(source)}"
    ]
    if page_range:
        details.append(
            f'<span style="flex:none;color:var(--text-color, #31333f);opacity:.7;'
            f'font-size:.8em">{html.escape(page_range)}</span>'
        )
    details.append("</header>")
    details.append(
        '<div class="source-markdown" style="margin-top:.4rem;line-height:1.45;'
        'overflow-wrap:anywhere">'
        f"{_render_markdown(text)}</div></article>"
    )
    return "".join(details)


def _relevance_score_html(source: dict[str, Any]) -> str:
    score = source.get("relevance_score")
    if (
        not isinstance(score, (int, float))
        or isinstance(score, bool)
        or not math.isfinite(score)
        or not 0.0 <= score <= 1.0
    ):
        return ""
    return (
        '<span class="relevance-score" title="Sigmoid re-ranker score; '
        'not a probability or confidence estimate">'
        f"Relevance {score:.2f}</span>"
    )


def citation_source_details(
    source: dict[str, Any], *, preview_limit: int | None = 100
) -> list[str]:
    source_id = source["id"]
    filename = (
        _source_filename(source) or source.get("file_title") or f"Source {source_id}"
    )
    lines = [filename]
    page_range = format_page_range(
        source.get("chunk_start_page_idx"), source.get("chunk_end_page_idx")
    )
    if page_range:
        lines.append(page_range)
    title = source.get("file_title")
    if title:
        lines.append(title)
    text = normalize_source_markdown(source.get("text", ""))
    if preview_limit is not None:
        text = text[:preview_limit].rstrip()
        if len(normalize_source_markdown(source.get("text", ""))) > preview_limit:
            text = f"{text}…"
    lines.extend(("", text))
    return lines


def format_page_range(start_index: int | None, end_index: int | None) -> str | None:
    start_page = start_index + 1 if start_index is not None else None
    end_page = end_index + 1 if end_index is not None else None
    if start_page is None and end_page is None:
        return None
    if start_page is None:
        return f"p. {end_page}"
    if end_page is None or end_page == start_page:
        return f"p. {start_page}"
    return f"p. {start_page}–{end_page}"


def normalize_source_markdown(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    normalized = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", normalized).strip()


def _render_markdown(text: str) -> str:
    return _MARKDOWN.render(text)


def _source_filename(source: dict[str, Any]) -> str | None:
    return source.get("original_file_name") or source.get("file_name")
