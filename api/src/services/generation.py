from collections.abc import Iterator
from common.helpers.llmfactory import create_llm
from ..models.query import GenerationConfig
from ..telemetry import telemetry

class GenerationService:
    def __init__(self, config, model: str | None = None):
        self.config = config
        self.llm_config = dict(config["llm"])
        if model is not None:
            self.llm_config["model"] = model
        self._llm = None

    def _get_llm(self):
        if self._llm is None:
            self._llm = create_llm(self.llm_config)
        return self._llm

    def generate(
        self,
        query: str,
        context: str,
        generation_config: GenerationConfig | None = None,
    ) -> str:
        with telemetry.span(
            "call llm", **self._generation_attributes(generation_config)
        ) as generate_span:

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
        prompt = self.prompt(query, context)
        generation_kwargs = self._generation_kwargs(generation_config)
        for chunk in telemetry.stream(
            "stream llm",
            lambda: self._get_llm().stream_complete(prompt, **generation_kwargs),
            self._generation_attributes(generation_config),
        ):
            yield str(getattr(chunk, "delta", getattr(chunk, "text", chunk)))

    @staticmethod
    def _generation_attributes(
        generation_config: GenerationConfig | None,
    ) -> dict[str, float | int]:
        if generation_config is None:
            return {}
        return generation_config.model_dump(exclude_none=True)

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

        * Each source chunk starts with 'Source [ID]' line, where ID is a numeric id of the source.
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

        Use the exact literal marker `[[source]]`, immediately followed by square brackets containing
        the numeric source ID or IDs from the retrieved sources. Do not replace `source` with another
        word, a source ID, or the placeholder `source_id`.

        For example, if a retrieved chunk is labeled `Source [7]`, use:

        `The source supports this claim. [[source]][7]`

        If the relevant chunks are labeled `Source [1]`, `Source [3]`, and `Source [7]`, cite multiple
        sources supporting the same sentence with a comma-separated list and no spaces:

        `[[source]][1,3,7]`

        For example: `The sources support this claim. [[source]][1,3,7]`

        The numbers must match the IDs in the `Source [number]` lines in the retrieved sources.
        
        ### Citation Rules:
            
        * Cite every factual sentence supported by the provided sources. If a sentence contains multiple
          factual claims, the citation must support all of them; include every relevant source ID in one
          citation block. If one sentence contains claims supported by different sources, include all
          those source IDs in that block.
        * Use only source IDs provided in the context. Never invent, modify, or guess a source ID.
        * Put the citation immediately after the sentence-ending punctuation (`.`, `?`, or `!`), with
          no punctuation between the sentence and citation. Do not put a citation before the punctuation.
        * When the answer has separate blocks, such as numbered items, bullets, or paragraphs, start each
          block on a new line. Put the line break after the citation block, not between the
          sentence punctuation and its citation. For example:

          `1. First point. [[source]][1]`
          `2. Second point. [[source]][2]`
        * Do not add whitespace inside the source-ID list.
        * Each source ID must contain only numbers; do not prefix IDs with `s`.
        * If a question cannot be answered from the sources, state this briefly and follow that sentence
          with the standalone citation block `[[source]][0]`. Use `0` only for this abstention marker:
          never combine it with real source IDs or use it to cite a factual claim.

        
        ## Query: 
        {query}
    
        ## Answer:
        '''
        return prompt
        
