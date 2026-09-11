'''
This is pymupdf based parser. Much faster compared to the pymupdf4llm based parser (pdfparser.py), good for text only pdf files.
However, doesn't handle tables and complex markdown as well as pdfparser.py
'''

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf


@dataclass
class Line:
    index: int #global line index
    page_index: int #page index where this line appears
    local_index: int #local line index on the page
    text: str
    start: int #start char index in pdf file
    end: int #end char index in pdf file (Exclusive)


@dataclass
class Heading:
    level: int
    title: str
    page_index: int
    line: Line | None = None #the line which corresponds to this heading


@dataclass
class SectionMetadata:
    section_title: str = ""
    section_start_char_idx: int = 0
    section_end_char_idx: int = 0
    file_name: str = ""
    file_path: str = ""
    file_title: str = ""
    file_author: str = ""
    file_length: int = 0
    file_total_pages: int = 0
    file_id: str = ""


@dataclass
class MarkdownSection:
    level: int
    text: str
    metadata: SectionMetadata

class PymupdfHelper:

    # extracts toc (list of headings) from the pdf doc
    def extract_toc(self, doc) -> list[Heading]:
        return [Heading(level=level,title=title,page_index=page-1) for level, title, page in doc.get_toc()]

    # extracts line text from raw line (across blocks and spans)
    def _extract_line_text(self, raw_line) -> str:
        chars = []

        for span in raw_line.get("spans", []):
            for char in span.get("chars", []):
                chars.append(char["c"])

        return "".join(chars)

    # Takes the pymupdf document and returns 
    # 1. the overall pdf text (character stream)
    # 2. the collection of lines in the pdf document (across pages)
    # 3. page range in terms of lines (start line index(inclusive), end line index(exclusive))
    def extract_document(
            self,
            doc,
        ) -> tuple[str, list[Line], dict[int, tuple[int, int]]]:
    
        lines = []
        text_parts = []
        page_ranges = []

        offset = 0

        for page_index, page in enumerate(doc):
            page_line_start_index = len(lines) #index of the first line on this page
            local_line_index = 0

            raw = page.get_text("rawdict")

            for block in raw.get("blocks", []):
                if block.get("type") != 0: #we only process text blocks (type=0) in this poc, ignore images (type=1)
                    continue

                for raw_line in block.get("lines", []):
                    text = self._extract_line_text(raw_line)

                    start, end = offset, offset + len(text)

                    #add to lines
                    lines.append(
                        Line(
                            index=len(lines),
                            page_index=page_index,
                            local_index=local_line_index,
                            text=text,
                            start=start,
                            end=end,
                        )
                    )

                    #add to text_parts
                    text_parts.append(text)

                    offset = end + 1 #to account for \n
                    local_line_index += 1

            #add start and end line index range for this page
            page_ranges.append((
                page_line_start_index,
                len(lines),
            ))

        #total document text is then all lines combined
        document_text = "\n".join(text_parts)

        return document_text, lines, page_ranges

class PdfParser:

    def _normalize(self, text: str) -> str:
        text = text.replace("\u00ad", "")
        text = text.lower()
        text = re.sub(r"\s+", " ", text)

        return text.strip()
    
    def _title_in_text(self, title: str, text: str,) -> bool:
        return self._normalize(title) in self._normalize(text)

    def _find_single_line_heading(self, lines: list[Line], title: str) -> Line | None:
    
        candidates = [
            line
            for line in lines
            if self._title_in_text(title, line.text)
        ]

        if not candidates:
            return None

        return min(
            candidates,
            key=lambda line: len(self._normalize(line.text)),
        )
    
    def _find_two_line_heading(self, lines: list[Line], title: str) -> Line | None:

        candidates = []

        for first, second in zip(lines, lines[1:]):
            combined = f"{first.text} {second.text}"

            if self._title_in_text(title, combined):
                candidates.append(first)

        if not candidates:
            return None

        return min(candidates, key=lambda line: len(self._normalize(line.text)))

    def _find_heading_on_page(self, lines: list[Line], title: str) -> Line | None:
    
        line = self._find_single_line_heading(lines, title)

        if line is not None:
            return line

        return self._find_two_line_heading(lines, title)

    def _resolve_heading(self, heading: Heading,lines: list[Line], page_ranges: list[tuple[int, int]], min_line_index: int) -> Line | None:
    
        if heading.page_index >= len(page_ranges):
            return None

        start, end = page_ranges[heading.page_index]

        start = max(start, min_line_index)

        if start >= end:
            return None

        page_lines = lines[start:end]

        return self._find_heading_on_page(page_lines, heading.title)

    def _resolve_headings(self, headings: list[Heading], lines: list[Line], page_ranges: list[tuple[int, int]]) -> None:

        min_line_index = 0

        for heading in headings:
            line = self._resolve_heading(heading, lines, page_ranges, min_line_index)

            if line is None:
                print(f"WARNING: Could not resolve TOC heading: ", f"{heading.title!r} ", f"(page {heading.page_index + 1})")
                continue

            heading.line = line
            min_line_index = line.index + 1


    def _build_hierarchical_sections(self, document_text: str, headings: list[Heading], doc, file_path: Path) -> list[MarkdownSection]:
    
            resolved_headings = [heading for heading in headings if heading.line is not None]
    
            sections = []
            pdf_metadata = doc.metadata or {}

            #add top level section for the full document
            sections.append(
                MarkdownSection(
                    level=0,
                    text=document_text,
                    metadata=SectionMetadata(
                        section_title=pdf_metadata.get("title", ""),
                        section_start_char_idx=0,
                        section_end_char_idx= len(document_text),
                        file_name=file_path.name,
                        file_path=str(file_path),
                        file_title=pdf_metadata.get("title", ""),
                        file_author=pdf_metadata.get("author", ""),
                        file_length=len(document_text),
                        file_total_pages=len(doc),
                    ),
                )
            )

            n = len(resolved_headings)

            #process each heading
            for i in range(n):
                heading = resolved_headings[i]
                start = heading.line.start

                #find the next heading with level <= current heading's level (to find the section end)
                j = i+1
                while j < n and resolved_headings[j].level > heading.level:
                    j += 1

                end = resolved_headings[j].line.start if (j < n) else len(document_text)
    
                metadata = SectionMetadata(
                    section_title=heading.title,
                    section_start_char_idx=start,
                    section_end_char_idx=end,
                    file_name=file_path.name,
                    file_path=str(file_path),
                    file_title=pdf_metadata.get("title", ""),
                    file_author=pdf_metadata.get("author", ""),
                    file_length=len(document_text),
                    file_total_pages=len(doc),
                )
    
                sections.append(
                    MarkdownSection(
                        level=heading.level,
                        text=document_text[start:end],
                        metadata=metadata,
                    )
                )
    
            return sections

    '''
    Takes the hierarchical sections and the cut_level and return a list of non-overlapping and collectively exhausting flat sections.
    All sections at level > cut_level are simply absorbed in their parent sections.
    For all the sections at level < cut_level (which are parent sections), their spans are adjusted so that they end right where
    the first child under them begins resulting in non-overlapping sections.
    '''
    def _get_flat_sections(self, sections, cut_level=2): 

        root = sections[0]
        markdown = root.text

        #remove (i.e merge with their parent) all sections at finer level than the cut level 
        flat_sections = [section for section in sections if section.level <= cut_level]

        #update end range and text for each parent section
        n = len(flat_sections)

        #process sections from end to start. set start_page and end_page for the last section
        next_section = flat_sections[-1]
        
        #process from second last to first sections
        for i in range(n-1)[::-1]: 
            curr_section = flat_sections[i]

            #if curr section is parent of next section, adjust current section's span so that it ends where the next section begins
            if curr_section.level < next_section.level: 

                curr_section.metadata.section_end_char_idx = next_section.metadata.section_start_char_idx

                #if this is the first section, just take everything from the start
                #this is to avoid extra \n at the beginning of the document
                if i == 0: 
                    curr_section.text = markdown[: curr_section.metadata.section_end_char_idx]
                else:
                    curr_section.text = markdown[curr_section.metadata.section_start_char_idx: curr_section.metadata.section_end_char_idx]


            #set curr as the next section for the next iteration
            next_section = curr_section
            
        return flat_sections

    def parse(self, file_path: str | Path, cut_level=2):
        file_path = Path(file_path)

        pymupdfhelper = PymupdfHelper()

        with pymupdf.open(file_path) as doc:
            document_text, lines, page_ranges = pymupdfhelper.extract_document(doc)

            #extract headings (logical sections) from the file 
            headings = pymupdfhelper.extract_toc(doc)

            #map each heading to the global line index in the pdf file
            self._resolve_headings(headings, lines, page_ranges)
            
            #create corresponding sections. A section starts where the new heading begins 
            # and ends one line before where the next section begins. 
            hierarchical_sections = self._build_hierarchical_sections(document_text, headings, doc, file_path)
            sections = self._get_flat_sections(hierarchical_sections, cut_level=cut_level)

            for section in sections:
                print(section.level,section.metadata.section_title ,section.metadata.section_start_char_idx, section.metadata.section_end_char_idx)

        return document_text, lines, headings, sections


# parser = PdfParser()
# parser.parse('staging/2505.07891.pdf')
# print('parser created..')


    