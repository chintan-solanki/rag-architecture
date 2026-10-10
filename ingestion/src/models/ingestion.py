from dataclasses import dataclass

@dataclass
class IndexChunk:
    chunk_id: str
    text: str

    start_char_idx: int = 0 #start index of chunk in the original pdf file character stream
    end_char_idx: int = 0 #end index of chunk in the original pdf file character stream
    start_page_idx: int = 0 #pdf page number index where the chunk starts
    end_page_idx: int = 0 #pdf page number index where the chunk ends

@dataclass
class IndexDocument:
    doc_id: str
    text:str
    metadata: any = None
