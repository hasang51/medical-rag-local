from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=3, ge=1, le=5)
    case_id: str | None = Field(default=None, pattern=r"^oracle-pilot-\d{3}$")

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("soru boş olamaz")
        return stripped


class EvidenceLayerItemSchema(BaseModel):
    citation_id: str
    layer: str
    title: str


class EvidenceLayersSchema(BaseModel):
    patient_cco: list[EvidenceLayerItemSchema] = Field(default_factory=list)
    snomed_terminology: list[EvidenceLayerItemSchema] = Field(default_factory=list)
    general_knowledge: list[EvidenceLayerItemSchema] = Field(default_factory=list)


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
    case_id: str | None = None
    intent: str = "legacy_dictionary"
    emergency: bool = False
    emergency_category: str | None = None
    evidence_layers: EvidenceLayersSchema = Field(default_factory=EvidenceLayersSchema)


class PatientProfileItem(BaseModel):
    case_id: str
    evaluated_at: str
    has_structured_data: bool
    total_rows: int
    value_fact_count: int
    missing_result_count: int
    families: list[str] = Field(default_factory=list)


class PatientsListResponse(BaseModel):
    patients: list[PatientProfileItem] = Field(default_factory=list)


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
