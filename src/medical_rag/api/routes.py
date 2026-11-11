import logging
import time

from fastapi import APIRouter, HTTPException, Request

from medical_rag.api.schemas import (
    ChatRequest,
    ChatResponse,
    CompleteRequest,
    CompleteResponse,
    HealthResponse,
)
from medical_rag.llm.ollama_client import OllamaError, OllamaTimeout
from medical_rag.rag.prompt import build_messages
from medical_rag.safety.policy import DISCLAIMER, abstain, enforce_contract

router = APIRouter()
logger = logging.getLogger("medical_rag.api")


def _log(event: str, **fields: object) -> None:
    # Soru metni ve model çıktısı buraya girmez.
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
