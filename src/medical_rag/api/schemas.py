from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=3, ge=1, le=5)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("soru boş olamaz")
        return stripped


class ChatResponse(BaseModel):
    answer: str
    citations: list[str]
    abstained: bool
    disclaimer: str
    eval_count: int = 0
    eval_duration_ns: int = 0
    total_duration_ns: int = 0
    done_reason: str = ""
    latency_ms: float
    retrieved_chunk_ids: list[str] = Field(default_factory=list)
    load_duration_ns: int = 0
    prompt_eval_count: int = 0
    prompt_eval_duration_ns: int = 0


class CompleteRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=500)

    @field_validator("prompt")
    @classmethod
    def strip_prompt(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("istem boş olamaz")
        return stripped


class CompleteResponse(BaseModel):
    text: str
    model: str
    num_ctx: int
    eval_count: int
    eval_duration_ns: int
    total_duration_ns: int


class HealthResponse(BaseModel):
    status: str
    ollama: str
    model: str
