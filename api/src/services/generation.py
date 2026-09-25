import os
from collections.abc import Iterable, Iterator
from ..telemetry import trace_span

class GenerationService:
    def __init__(self, config, model: str | None = None):
        self.config = config
        self.model = model or config['llm']['model']
        self._llm = None

    def _get_llm(self):
        if self._llm is None:
            from llama_index.llms.openai import OpenAI
            self._llm = OpenAI(model=self.model, api_key=os.getenv("OPENAI_API_KEY"))
        return self._llm

    def generate(self, query: str, context: str) -> str:
        with trace_span('call llm') as generate_span:

            llm_prompt = self.prompt(query, context)
            response = self._get_llm().complete(llm_prompt)
            ret = str(getattr(response, "text", response))

            generate_span.set_attributes({
                'prompt': llm_prompt,
                'response': ret
            })
            return ret

    def stream(self, query: str, context: str) -> Iterator[str]:
        response = self._get_llm().stream_complete(self.prompt(query, context))
        for chunk in response:
            yield str(getattr(chunk, "delta", getattr(chunk, "text", chunk)))


    @staticmethod
    def prompt(query: str, context: str) -> str:

        prompt = f'''
        
        Please answer the query based on the provided context.
        Every time you use a source text to generate your answer part, you must add the corresponding citation source in the following way.
        
        ### Citation format
    
        `[[cite]][source_id]`
    
        For multiple sources, use a comma-separated list:
    
        `[[cite]][s1,s3,s7]`
    
        Rules:
    
        * Cite factual claims when they are supported by the provided sources.
        * Use only source IDs provided in the context. Never invent, modify, or guess a source ID.
        * Place the citation immediately after the claim it supports.
        * Ensure citation appears only after completed sentences (after . and ?, not before them)
        * Do not add whitespace inside the source-ID list.
        * Each source ID may contain only numbers
    
        ### Escaping
    
        `[[cite]]` is reserved for citations.
    
        To output citation syntax as literal text, prefix `[[cite]]` with one backslash:
    
        `\\[[cite]][s1]`
    
        The backslash is special **only when it immediately precedes `[[cite]]`**. Otherwise, preserve backslashes exactly as written, including those in code, file paths, regular expressions, and LaTeX.
    
        Do not use external knowledge to answer the question. If you do not know the answer, send empty response.
        All parts of your answer must be backed by ciations.
    
        ### Context:
        {context}
    
        ### Query: 
        {query}
    
        ### Answer:
        '''
        return prompt
        
