import os

from models.ingestion import IndexChunk, IndexDocument
from .chunkcontextheader import ChunkContextHeader
import dicttoxml

class ChunkContextualizedSummaryGenerator:

    '''
    Generates contextualized summary for the chunk header. 
    The summary is generated using the section text and chunk text.
    '''
    def __init__(self, model: str, llm=None):
        self.model = model
        self._llm = llm

    def _get_llm(self):
        if self._llm is None:
            from llama_index.llms.openai import OpenAI

            self._llm = OpenAI(
                model=self.model,
                api_key=os.getenv("OPENAI_API_KEY"),
            )
        return self._llm

    def get_context_header(self, chunk: IndexChunk, document: IndexDocument, comment: str = None) -> ChunkContextHeader:

        comment_str = ''
        if comment:
            comment_str = f'<comment>{comment}</comment>'
        
        prompt = f"""
<document>
    <text>{document.text}</text>
    {comment_str}                            
</document>

Here is the chunk we want to situate within the whole document:
<chunk>
{chunk.text}
</chunk>

Please give a short succinct context to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk. Answer only with the succinct context and nothing else. The comment field, if present, describes and may provide context about the whole document.
"""
        response = self._get_llm().complete(prompt)
        summary = str(getattr(response, "text", response)).strip()

        if not summary:
            raise RuntimeError("The LLM returned an empty contextualized chunk summary.")

        header = ChunkContextHeader()
        header.summary = summary
        header.comment = comment
        
        return header