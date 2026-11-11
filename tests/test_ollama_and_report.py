import asyncio
import json

import httpx
import pytest

from medical_rag.config import Settings
from medical_rag.eval.report import (
    assert_acceptance,
    build_record,
    cpu_gpu_comparison,
    generation_truncated,
    percentile_95,
    profile_records,
    refuse_baseline_overwrite,
    summarize,
    tokens_per_second,
)
from medical_rag.llm.ollama_client import OllamaClient
from medical_rag.safety.policy import DISCLAIMER


def _record(index: int, latency: float) -> dict[str, object]:
    return {
        "question_id": f"q{index:02d}",
        "disclaimer": DISCLAIMER,
        "abstained": False,
        "citations": ["kan-basinci-0"],
        "uncited_claim": 0,
        "latency_ms": latency,
        "eval_count": 10,
        "eval_duration_ns": 5_000_000_000,
        "tokens_per_second": 2.0,
    }


def test_summary_math() -> None:
    records = [_record(index, float(index * 1000)) for index in range(1, 11)]
    summary = summarize(records)
    assert summary["count"] == 10
    assert summary["uncited_claim_count"] == 0
    assert summary["disclaimer_present_count"] == 10
    assert summary["p95_latency_ms"] == percentile_95([float(index * 1000) for index in range(1, 11)])
    assert summary["tokens_per_second"] == pytest.approx(100 / 50)
    payload = {"records": records, "summary": summary}
    assert_acceptance(payload)


def test_tokens_per_second_is_zero_without_generation() -> None:
    assert tokens_per_second(0, 0) == 0.0


def test_chat_payload_pins_context_and_is_single_flight() -> None:
    active = 0
    peak = 0
    seen_ctx: list[int] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, peak
        payload = json.loads(request.content.decode())
        seen_ctx.append(payload["options"]["num_ctx"])
        assert payload["think"] is False
        assert "think" not in payload["options"]
        assert payload["options"]["num_predict"] == 128
        assert payload["options"]["temperature"] == 0.2
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.05)
        active -= 1
        return httpx.Response(
            200,
            json={
                "model": "gemma4:e4b",
                "message": {"role": "assistant", "content": "tamam"},
                "eval_count": 2,
                "eval_duration": 1_000_000_000,
                "total_duration": 1_000_000_000,
            },
        )

    async def scenario() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http:
            client = OllamaClient(Settings(), http)
            await asyncio.gather(
                client.chat([{"role": "user", "content": "bir"}]),
                client.chat([{"role": "user", "content": "iki"}]),
            )

    asyncio.run(scenario())
    assert peak == 1
    assert seen_ctx == [2048, 2048]


def test_predict_and_think_stay_configurable() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "model": "gemma4:e4b",
                "message": {"role": "assistant", "content": "tamam"},
                "eval_count": 1,
                "eval_duration": 1,
                "total_duration": 1,
                "done_reason": "stop",
            },
        )

    async def scenario() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http:
            await OllamaClient(Settings(num_predict=512, think=True), http).chat(
                [{"role": "user", "content": "kıyas"}]
            )

    asyncio.run(scenario())
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["think"] is True
    assert body["options"]["num_predict"] == 512
    assert body["options"]["num_ctx"] == 2048
    assert body["options"]["temperature"] == 0.2


def test_profile_compares_old_and_new_records() -> None:
    old = [
        {
            "latency_ms": 1000.0,
            "eval_count": 512,
            "eval_duration_ns": 10,
            "abstained": True,
            "citations": [],
        },
        {
            "latency_ms": 3000.0,
            "eval_count": 100,
            "eval_duration_ns": 10,
            "abstained": False,
            "citations": ["nabiz-0"],
        },
    ]
    old_profile = profile_records(old, truncation_cap=512)
    assert old_profile["total_duration_ns_sum"] is None
    assert old_profile["truncation_rate"] == 0.5
    assert old_profile["citation_rate"] == 0.5
    assert old_profile["abstention_rate"] == 0.5
    assert old_profile["p50_latency_ms"] == 1000.0

    new = [
        {
            "latency_ms": 400.0,
            "eval_count": 128,
            "eval_duration_ns": 10,
            "total_duration_ns": 20,
            "abstained": False,
            "citations": ["ates-0"],
            "truncated": True,
        }
    ]
    new_profile = profile_records(new)
    assert new_profile["total_duration_ns_sum"] == 20
    assert new_profile["truncation_rate"] == 1.0
    assert generation_truncated(128, 128, "stop") is False
    assert generation_truncated(128, 128, "length") is True
    assert generation_truncated(128, 128, "") is True


def test_client_keeps_prompt_and_load_timings() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "gemma4:e4b",
                "message": {"role": "assistant", "content": "tamam"},
                "done_reason": "stop",
                "load_duration": 15,
                "prompt_eval_count": 32,
                "prompt_eval_duration": 2_000_000_000,
                "eval_count": 4,
                "eval_duration": 1_000_000_000,
                "total_duration": 3_000_000_000,
            },
        )

    async def scenario():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http:
            return await OllamaClient(Settings(), http).chat([{"role": "user", "content": "ölç"}])

    completion = asyncio.run(scenario())
    assert completion.load_duration_ns == 15
    assert completion.prompt_eval_count == 32
    assert completion.prompt_eval_duration_ns == 2_000_000_000
    assert completion.done_reason == "stop"


def test_record_marks_expected_source_without_changing_safety_fields() -> None:
    record = build_record(
        {"id": "q01", "expected_chunk_id": "kan-basinci-0"},
        {
            "disclaimer": DISCLAIMER,
            "abstained": False,
            "citations": ["kan-basinci-0"],
            "retrieved_chunk_ids": ["kan-basinci-0", "nabiz-0"],
            "latency_ms": 12.5,
            "load_duration_ns": 3,
            "prompt_eval_count": 20,
            "prompt_eval_duration_ns": 2_000_000_000,
            "eval_count": 8,
            "eval_duration_ns": 1_000_000_000,
            "total_duration_ns": 4,
            "done_reason": "stop",
        },
        128,
    )
    assert record["expected_source_retrieved"] is True
    assert record["expected_source_cited"] is True
    assert record["uncited_claim"] == 0
    assert record["truncated"] is False
    assert record["prompt_tokens_per_second"] == pytest.approx(10.0)
    assert record["tokens_per_second"] == pytest.approx(8.0)


def test_cpu_comparison_leaves_missing_prompt_throughput_empty() -> None:
    questions = [{"id": "q01", "expected_chunk_id": "kan-basinci-0", "expect_hit": True}]
    cpu = {
        "model": "gemma4:e4b",
        "records": [
            {
                "question_id": "q01",
                "latency_ms": 1000.0,
                "eval_count": 10,
                "eval_duration_ns": 2_000_000_000,
                "abstained": False,
                "citations": ["kan-basinci-0"],
                "truncated": False,
            }
        ],
    }
    gpu = {
        "model": "gemma4:e4b",
        "records": [
            {
                "question_id": "q01",
                "latency_ms": 100.0,
                "eval_count": 10,
                "eval_duration_ns": 1_000_000_000,
                "prompt_eval_count": 20,
                "prompt_eval_duration_ns": 2_000_000_000,
                "abstained": False,
                "citations": ["kan-basinci-0"],
                "retrieved_chunk_ids": ["kan-basinci-0"],
                "truncated": False,
            }
        ],
    }
    compared = cpu_gpu_comparison(cpu, gpu, questions, cpu_source="cpu.json", gpu_source="gpu.json")
    assert compared["cpu"]["prompt_tokens_per_second"] is None
    assert compared["cpu"]["expected_source_retrieved_count"] is None
    assert compared["cpu"]["expected_source_cited_count"] == 1
    assert compared["gpu"]["prompt_tokens_per_second"] == pytest.approx(10.0)
    assert compared["gpu"]["expected_source_retrieved_count"] == 1
    assert "klinik doğruluk kanıtlamaz" in str(compared["citation_presence_note"])


def test_baseline_filenames_cannot_be_the_gpu_target(tmp_path) -> None:
    baseline = tmp_path / "runtime"
    baseline.mkdir()
    with pytest.raises(RuntimeError):
        refuse_baseline_overwrite(baseline / "eval_report.json", baseline)
    refuse_baseline_overwrite(baseline / "gpu-a40-v1" / "eval_report.json", baseline)


def test_health_treats_connection_failure_as_down() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("kapalı")

    async def scenario() -> bool:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http:
            return await OllamaClient(Settings(), http).health()

    assert asyncio.run(scenario()) is False
