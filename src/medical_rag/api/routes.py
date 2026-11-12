import logging
import time

from fastapi import APIRouter, HTTPException, Request

from medical_rag.api.schemas import (
    ChatRequest,
    ChatResponse,
    CompleteRequest,
    CompleteResponse,
    EvidenceLayerItemSchema,
    EvidenceLayersSchema,
    HealthResponse,
    PatientProfileItem,
    PatientsListResponse,
)
from medical_rag.llm.ollama_client import OllamaError, OllamaTimeout
from medical_rag.rag.prompt import build_messages, build_twin_messages
from medical_rag.safety.emergency import check_emergency
from medical_rag.safety.policy import (
    DISCLAIMER,
    abstain,
    enforce_contract,
    enforce_twin_contract,
)

router = APIRouter()
logger = logging.getLogger("medical_rag.api")


def _log(event: str, **fields: object) -> None:
    # Soru metni, ham klinik değerler, opak kimlikler ve model çıktısı buraya girmez.
    tail = " ".join(f"{key}={value}" for key, value in fields.items())
    logger.info("%s %s", event, tail)


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    started = time.perf_counter()
    reachable = await request.app.state.ollama.health()
    status = "ok" if reachable else "degraded"
    _log(
        "health",
        status=status,
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
    )
    return HealthResponse(
        status=status,
        ollama="ok" if reachable else "unreachable",
        model=settings.model,
    )


@router.get("/v1/patients", response_model=PatientsListResponse)
async def list_patients(request: Request) -> PatientsListResponse:
    """Anonim Digital Twin vaka listesini ve özet satır sayılarını döndürür."""
    started = time.perf_counter()
    twin = request.app.state.twin
    summaries = twin.list_patients()
    _log(
        "patients",
        status=200,
        count=len(summaries),
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
    )
    return PatientsListResponse(
        patients=[
            PatientProfileItem(
                case_id=item.case_id,
                evaluated_at=item.evaluated_at,
                has_structured_data=item.has_structured_data,
                total_rows=item.total_rows,
                value_fact_count=item.value_fact_count,
                missing_result_count=item.missing_result_count,
                families=item.families,
            )
            for item in summaries
        ]
    )


@router.post("/v1/complete", response_model=CompleteResponse)
async def complete(body: CompleteRequest, request: Request) -> CompleteResponse:
    """RAG'siz duman ucu. Model ayakta mı ve num_ctx gerçekten 2048 mi, onu gösterir."""
    settings = request.app.state.settings
    started = time.perf_counter()
    try:
        completion = await request.app.state.ollama.chat(
            [{"role": "user", "content": body.prompt}],
            num_predict=settings.smoke_num_predict,
        )
    except OllamaTimeout:
        _log("complete", code="ollama_timeout")
        raise HTTPException(status_code=504, detail="model zaman aşımı") from None
    except OllamaError as exc:
        _log("complete", code=exc.code)
        raise HTTPException(status_code=503, detail="model erişilemez") from None
    _log(
        "complete",
        status=200,
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
        eval_count=completion.eval_count,
        num_ctx=completion.num_ctx,
    )
    return CompleteResponse(
        text=completion.text,
        model=completion.model,
        num_ctx=completion.num_ctx,
        eval_count=completion.eval_count,
        eval_duration_ns=completion.eval_duration_ns,
        total_duration_ns=completion.total_duration_ns,
    )


@router.post("/v1/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request) -> ChatResponse:
    started = time.perf_counter()

    # 1. Modelden Önce Deterministik Acil Durum Denetimi (Her iki modda da çalışır)
    emergency = check_emergency(body.question)
    if emergency.is_emergency:
        latency_ms = (time.perf_counter() - started) * 1000
        _log(
            "chat",
            status=200,
            duration_ms=round(latency_ms, 1),
            intent="emergency",
            emergency=True,
            category=emergency.category,
            eval_count=0,
        )
        return ChatResponse(
            answer=emergency.message,
            citations=[],
            abstained=False,
            disclaimer=DISCLAIMER,
            latency_ms=latency_ms,
            retrieved_chunk_ids=[],
            case_id=body.case_id,
            intent="emergency",
            emergency=True,
            emergency_category=emergency.category,
        )

    # 2. Mevcut Genel Sözlük Baseline Modu (case_id verilmediğinde birebir korunur)
    if body.case_id is None:
        hits = request.app.state.retriever.retrieve(body.question, body.top_k)
        if not hits:
            decision = abstain()
            latency_ms = (time.perf_counter() - started) * 1000
            _log(
                "chat",
                status=200,
                duration_ms=round(latency_ms, 1),
                abstained=True,
                citations="",
                eval_count=0,
            )
            return ChatResponse(
                answer=decision.answer,
                citations=[],
                abstained=True,
                disclaimer=DISCLAIMER,
                latency_ms=latency_ms,
                retrieved_chunk_ids=[],
            )

        try:
            completion = await request.app.state.ollama.chat(
                build_messages(body.question, hits)
            )
        except OllamaTimeout:
            _log("chat", code="ollama_timeout", citations=",".join(hit.id for hit in hits))
            raise HTTPException(status_code=504, detail="model zaman aşımı") from None
        except OllamaError as exc:
            _log("chat", code=exc.code, citations=",".join(hit.id for hit in hits))
            raise HTTPException(status_code=503, detail="model erişilemez") from None

        decision = enforce_contract(completion.text, [hit.id for hit in hits])
        latency_ms = (time.perf_counter() - started) * 1000
        _log(
            "chat",
            status=200,
            duration_ms=round(latency_ms, 1),
            abstained=decision.abstained,
            citations=",".join(decision.citations),
            eval_count=completion.eval_count,
        )
        return ChatResponse(
            answer=decision.answer,
            citations=decision.citations,
            abstained=decision.abstained,
            disclaimer=DISCLAIMER,
            eval_count=completion.eval_count,
            eval_duration_ns=completion.eval_duration_ns,
            total_duration_ns=completion.total_duration_ns,
            done_reason=completion.done_reason,
            latency_ms=latency_ms,
            retrieved_chunk_ids=[hit.id for hit in hits],
            load_duration_ns=completion.load_duration_ns,
            prompt_eval_count=completion.prompt_eval_count,
            prompt_eval_duration_ns=completion.prompt_eval_duration_ns,
        )

    # 3. G5 Kişisel Digital Twin Modu (CCO + SNOMED CT IPS + Genel Sözlük)
    settings = request.app.state.settings
    twin = request.app.state.twin
    prepared = twin.prepare_turn(
        body.question,
        case_id=body.case_id,
        retriever=request.app.state.retriever,
        top_k=body.top_k,
    )

    if prepared.patient is None:
        raise HTTPException(status_code=404, detail="hasta profili bulunamadı")

    layers_schema = EvidenceLayersSchema(
        patient_cco=[
            EvidenceLayerItemSchema(
                citation_id=item.citation_id, layer=item.layer, title=item.title
            )
            for item in prepared.evidence.patient_cco
        ],
        snomed_terminology=[
            EvidenceLayerItemSchema(
                citation_id=item.citation_id, layer=item.layer, title=item.title
            )
            for item in prepared.evidence.snomed_terminology
        ],
        general_knowledge=[
            EvidenceLayerItemSchema(
                citation_id=item.citation_id, layer=item.layer, title=item.title
            )
            for item in prepared.evidence.general_knowledge
        ],
    )
    allowed_ids = prepared.evidence.allowed_citation_ids

    if prepared.plan.intent == "out_of_scope" or not allowed_ids:
        decision = abstain()
        latency_ms = (time.perf_counter() - started) * 1000
        _log(
            "chat",
            status=200,
            duration_ms=round(latency_ms, 1),
            mode="twin",
            intent=prepared.plan.intent,
            abstained=True,
            eval_count=0,
        )
        return ChatResponse(
            answer=decision.answer,
            citations=[],
            abstained=True,
            disclaimer=DISCLAIMER,
            latency_ms=latency_ms,
            retrieved_chunk_ids=[],
            case_id=body.case_id,
            intent=prepared.plan.intent,
        )

    if prepared.history_answer:
        decision = enforce_twin_contract(prepared.history_answer, allowed_ids)
        latency_ms = (time.perf_counter() - started) * 1000
        _log(
            "chat",
            status=200,
            duration_ms=round(latency_ms, 1),
            mode="twin",
            intent=prepared.plan.intent,
            abstained=decision.abstained,
            citation_count=len(decision.citations),
            eval_count=0,
        )
        return ChatResponse(
            answer=decision.answer,
            citations=decision.citations,
            abstained=decision.abstained,
            disclaimer=DISCLAIMER,
            eval_count=0,
            latency_ms=latency_ms,
            retrieved_chunk_ids=allowed_ids,
            case_id=body.case_id,
            intent=prepared.plan.intent,
            evidence_layers=layers_schema,
        )

    try:
        completion = await request.app.state.ollama.chat(
            build_twin_messages(body.question, prepared.rendered_context),
            num_ctx=settings.twin_num_ctx,
            num_predict=settings.twin_num_predict,
        )
    except OllamaTimeout:
        _log("chat", code="ollama_timeout", mode="twin", intent=prepared.plan.intent)
        raise HTTPException(status_code=504, detail="model zaman aşımı") from None
    except OllamaError as exc:
        _log("chat", code=exc.code, mode="twin", intent=prepared.plan.intent)
        raise HTTPException(status_code=503, detail="model erişilemez") from None

    decision = enforce_twin_contract(completion.text, allowed_ids)
    latency_ms = (time.perf_counter() - started) * 1000
    _log(
        "chat",
        status=200,
        duration_ms=round(latency_ms, 1),
        mode="twin",
        intent=prepared.plan.intent,
        abstained=decision.abstained,
        citation_count=len(decision.citations),
        eval_count=completion.eval_count,
    )
    return ChatResponse(
        answer=decision.answer,
        citations=decision.citations,
        abstained=decision.abstained,
        disclaimer=DISCLAIMER,
        eval_count=completion.eval_count,
        eval_duration_ns=completion.eval_duration_ns,
        total_duration_ns=completion.total_duration_ns,
        done_reason=completion.done_reason,
        latency_ms=latency_ms,
        retrieved_chunk_ids=allowed_ids,
        load_duration_ns=completion.load_duration_ns,
        prompt_eval_count=completion.prompt_eval_count,
        prompt_eval_duration_ns=completion.prompt_eval_duration_ns,
        case_id=body.case_id,
        intent=prepared.plan.intent,
        evidence_layers=layers_schema,
    )
