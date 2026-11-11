from medical_rag.llm.ollama_client import Completion
from medical_rag.rag.retriever import ScoredChunk


class FakeOllama:
    def __init__(
        self,
        *,
        healthy: bool = True,
        text: str = "",
        fail: Exception | None = None,
        load_duration_ns: int = 0,
        prompt_eval_count: int = 0,
        prompt_eval_duration_ns: int = 0,
    ) -> None:
        self.healthy = healthy
        self.text = text
        self.fail = fail
        self.calls = 0
        self.last_num_predict: int | None = None
        self.load_duration_ns = load_duration_ns
        self.prompt_eval_count = prompt_eval_count
        self.prompt_eval_duration_ns = prompt_eval_duration_ns

    async def health(self) -> bool:
        return self.healthy

    async def chat(self, messages, *, num_predict=None):
        self.calls += 1
        self.last_num_predict = num_predict
        if self.fail is not None:
            raise self.fail
        return Completion(
            text=self.text,
            model="gemma4:e4b",
            num_ctx=2048,
            eval_count=4,
            eval_duration_ns=2_000_000_000,
            total_duration_ns=3_000_000_000,
            load_duration_ns=self.load_duration_ns,
            prompt_eval_count=self.prompt_eval_count,
            prompt_eval_duration_ns=self.prompt_eval_duration_ns,
        )


class ScriptedRetriever:
    def __init__(self, hits: list[ScoredChunk]) -> None:
        self.hits = hits

    def retrieve(self, query: str, top_k: int) -> list[ScoredChunk]:
        return self.hits[:top_k]
