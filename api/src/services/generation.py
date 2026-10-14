import os
from collections.abc import Iterable, Iterator
from ..models.query import GenerationConfig
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

    def generate(
        self,
        query: str,
        context: str,
        generation_config: GenerationConfig | None = None,
    ) -> str:
        with trace_span('call llm') as generate_span:

            llm_prompt = self.prompt(query, context)
            response = self._get_llm().complete(
                llm_prompt, **self._generation_kwargs(generation_config)
            )
            ret = str(getattr(response, "text", response))

            generate_span.set_attributes({
                'prompt': llm_prompt,
                'response': ret
            })
            return ret

    def stream(
        self,
        query: str,
        context: str,
        generation_config: GenerationConfig | None = None,
    ) -> Iterator[str]:
        response = self._get_llm().stream_complete(
            self.prompt(query, context),
            **self._generation_kwargs(generation_config),
        )
        for chunk in response:
            yield str(getattr(chunk, "delta", getattr(chunk, "text", chunk)))

    @staticmethod
    def _generation_kwargs(
        generation_config: GenerationConfig | None,
    ) -> dict[str, float | int]:
        if generation_config is None:
            return {}

        kwargs: dict[str, float | int] = {}
        if generation_config.temperature is not None:
            kwargs["temperature"] = generation_config.temperature
        if generation_config.top_p is not None:
            kwargs["top_p"] = generation_config.top_p
        if generation_config.max_output_tokens is not None:
            kwargs["max_tokens"] = generation_config.max_output_tokens
        return kwargs

    @staticmethod
    def prompt(query: str, context: str) -> str:

        prompt = f'''
        
        ## Instructions

        Please answer the query based on the provided source chunks (or in short referred as source). 
        Every time you use a source text to generate your answer part, you must add the corresponding citation in your answer.
        
        ### Structure of source chunks

        * Each source chunk starts with 'Source [source_id]' line, where source_id is a numeric id of the source. 
        * Then next few lines contain <ChunkContext>..</ChunkContext> block, which provides summary details about the source chunk.
        * The actual source chunk text follows.

        ### Validity of Sources.
        
        * Do not blindly answer based on the retrieved source chunk.
        * The source chunks are retrieved by a retrieval system which may retrieve spurious chunks; chunks which match the keywords and structure in the query but may still be completely irrelevant or worse yet, may relate to a completely different entity than the one referred to in the question. 
        * Use information inside <ChunkContext> to establish and decide if a source chunk is applicable to the question asked and can be used to generate the answer/a part of the answer.
        * If the question or a part of the question cannot be reliably answered by any of the source chunks, you must state so in your answer.

        ### structure of query.
        
        * The user may ask a single query or combine multiple questions into a single query.
        * Answer each question independently, whether or not the questions are related.
        * Answer a question only when the retrieved sources reliably support the answer.
        * If a question cannot be answered reliably from the retrieved sources, say so briefly and use the null-source marker described below. Do not guess or let an answer to one question influence whether you answer another.

        ### Answer rules
        * Do not use external knowledge to answer the question. 
        * Cite every factual claim that is supported by the sources.
        * An explicit statement that a question cannot be answered from the provided sources is an allowed abstention, not a source-backed factual claim.
            
        ## Retrieved Sources:
        {context}
    
        ### Citation format
            
        `[[cite]][1]`
    
        For multiple sources, use a comma-separated list:
    
        `[[cite]][1,3,7]`
    
        Here the number(s) inside the single square brackets are the source ids listed against each retrieved source.
        
        ### Citation Rules:
            
        * Cite factual claims when they are supported by the provided sources.
        * Use only source IDs provided in the context. Never invent, modify, or guess a source ID.
        * Place the citation immediately after the claim it supports.
        * Ensure citation appears only after completed sentences (after . and ?, not before them)
        * Do not add whitespace inside the source-ID list.
        * Each source ID may contain only numbers; do not prefix IDs with `s`.
        * For an unanswerable question, state that it cannot be answered from the provided sources and follow that statement with the standalone citation block `[[cite]][0]`.
        * `0` is a special null-source marker, not a source ID. Never combine it with real source IDs or use it to cite a factual claim.

        
        ## Query: 
        {query}
    
        ## Answer:
        '''
        return prompt
        
