from dataclasses import dataclass
from markdown_it import MarkdownIt
from bisect import bisect_left, bisect_right
from collections import defaultdict

import pymupdf4llm
from markdown_it import MarkdownIt
from pathlib import Path


@dataclass
class SectionMetadata:

    #section level metadata
    section_title: str = ''
    section_start_char_idx: int = 0 #index in pdf document text where the section starts
    section_end_char_idx: int = 0 #index in pdf document text where the section ends

    #file (to which the section belongs) level metadata
    file_name: str = '' 
    file_path: str = ''
    file_title: str = ''
    file_author: str = ''
    file_length: int = 0 #no of characters in pdf file
    file_total_pages: int = 0 #total pages in the parent document
    
@dataclass
class MarkdownSection:

    level: int
    text: str
    
    metadata: SectionMetadata


class PdfParser:

    '''
    returns start character indexes for each page (0-based). 
    '''
    def _build_page_offsets(self, pages):
        offsets = []
        start = 0

        for i, page in enumerate(pages):
            offsets.append(start)
            start = start + len(page['text'])
        return offsets


    '''
    returns pdf file level metadata and page_offsets (mapping between pages and their start character positions)
    '''
    def _get_pdf_metadata(self, file_path_str, pages):

        metadata = defaultdict(None)

        if file_path_str and (file_path := Path(file_path_str)).exists():
            metadata['file_name'] = file_path.name
            metadata['file_path'] = str(file_path)

        src_obj = pages[0]['metadata']
        metadata['file_author'] = src_obj.get('author', '')
        metadata['file_title'] = src_obj.get('title', '')
        metadata['file_page_count'] = src_obj.get('page_count', 0)
        metadata['file_length'] = sum((len(page['text']) for page in pages))

        page_offsets = self._build_page_offsets(pages)
        return metadata, page_offsets

    '''
    returns index for each new line character (0 based) 
    Note that if there are 'm' newline characters (\n), then we have m+1 lines.
    so offsets[i] = character index of ith line (0 based) 
    '''
    def _build_line_offsets(self, text):
        
        offsets = [0] #first line always start at 0th index

        for i, char in enumerate(text):
            if char == "\n":
                offsets.append(i)

        return offsets

    '''
    takes markdown and and returns the list of heirarchical sections
    '''
    def _markdown_sections(self, markdown, file_metadata):

        md = MarkdownIt("commonmark")
        tokens = md.parse(markdown)
        line_offsets = self._build_line_offsets(markdown)
        headings = []

        # pass 1: extract each heading (often heirarchical), its level and start line
        for i, token in enumerate(tokens):

            if token.type != "heading_open":
                continue

            level = int(token.tag[1]) #e.g for h1, level=1

            # <heading_open> <inline> <heading_close>
            inline_token = tokens[i + 1]
            section_title = inline_token.content
            start_line = token.map[0]

            headings.append({
                "level": level,
                "section_title": section_title,
                "start_line": start_line, 
            })

        # pass 2: create sections from the headings. A section defined by a heading at level l ends when we encounter the 
        # first heading with level <= l (or the end of text)
        # note that start_line, start_idx are inclusive, end_line, end_idx are exclusive
        sections = []
        n = len(headings)

        for i in range(n): #for each heading index
            heading = headings[i]
            level = heading["level"]
            start_line = heading["start_line"]

            # Find the next heading with the same or lower level. That ends the current section
            end_line = len(line_offsets)
            for j in range(i+1, n):
                next_heading = headings[j]
                if next_heading["level"] <= level: #new section start detected. it's start is the end of the current section
                    end_line = next_heading["start_line"]
                    break

            #map the section start and end lines to start and end character positions 
            start_idx = line_offsets[start_line]

            if end_line < len(line_offsets):
                end_idx = line_offsets[end_line]
            else:
                end_idx = len(markdown)

            sections.append(
                MarkdownSection(
                    level=level,
                    text=markdown[start_idx:end_idx],

                    metadata=SectionMetadata(
                        section_title=heading["section_title"],
                        section_start_char_idx = start_idx,
                        section_end_char_idx = end_idx,

                        file_name=file_metadata.get('file_name', ''), 
                        file_path=file_metadata.get('file_path', ''), 
                        file_title=file_metadata.get('file_title', ''), 
                        file_author=file_metadata.get('file_author', ''),
                        file_total_pages=file_metadata.get('file_total_pages', ''), 
                        file_length=len(markdown),
                        
                    )
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


    '''
    Takes a pdf file path and returns a list of sections (at specified cut level) with their text and metadata. Each section is a MarkdownSection object. 
    '''
    def parse(self, file_path, cut_level=2):
        pages = pymupdf4llm.to_markdown(file_path, page_chunks=True)
        full_md = ''.join([page['text'] for page in pages])

        file_metadata, file_page_offsets = self._get_pdf_metadata(file_path, pages)

        #parse the markdown to find logical sections (treating h2 as the cut_level)
        hierarchical_sections = self._markdown_sections(full_md, file_metadata)
        sections = self._get_flat_sections(hierarchical_sections, cut_level=cut_level)

        return file_metadata, file_page_offsets, sections

