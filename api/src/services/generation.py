import os
from collections.abc import Iterable, Iterator

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

    @staticmethod
    def prompt(query: str, context: str) -> str:
        return (
            "Answer only from the context below. Cite claims using exactly [[cite]][1,2]. "
            "Use only the supplied source IDs. Return ordinary text, never JSON.\n\n"
            f"Context:\n{context}\n\nQuestion: {query}"
        )

    def generate(self, query: str, context: str) -> str:
        response = self._get_llm().complete(self.prompt(query, context))
        return str(getattr(response, "text", response))

    def stream(self, query: str, context: str) -> Iterator[str]:
        response = self._get_llm().stream_complete(self.prompt(query, context))
        for chunk in response:
            yield str(getattr(chunk, "delta", getattr(chunk, "text", chunk)))
