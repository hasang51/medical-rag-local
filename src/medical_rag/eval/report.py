import csv
import json
import math
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from medical_rag.config import Settings
from medical_rag.main import create_app
from medical_rag.safety.policy import DISCLAIMER


def percentile_nearest(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    # En yakın sıra: ceil(p * n). On kayıtta p95, en yavaş turdur.
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def percentile_95(values: list[float]) -> float:
    return percentile_nearest(values, 0.95)


def generation_truncated(eval_count: int, num_predict: int, done_reason: str) -> bool:
    """Durma nedeni length ise tavan kesmiştir. stop, doğal bitiştir.

    Eski Ollama gövdesi done_reason taşımazsa eval_count tavanı vekil olur.
    """
    if done_reason == "length":
        return True
    if done_reason == "stop" or eval_count <= 0:
        return False
    return eval_count >= num_predict


def tokens_per_second(eval_count: int, eval_duration_ns: int) -> float:
    if eval_count <= 0 or eval_duration_ns <= 0:
        return 0.0
    return eval_count / (eval_duration_ns / 1_000_000_000)


def build_record(
    item: dict[str, object],
    body: dict[str, object],
    num_predict: int,
) -> dict[str, object]:
    """Tek sorunun ölçüm satırı. Güvenlik kararı çağrı gövdesinden okunur."""
    eval_count = int(body["eval_count"])
    eval_duration_ns = int(body["eval_duration_ns"])
    done_reason = str(body.get("done_reason") or "")
    raw_citations = body["citations"]
    if not isinstance(raw_citations, list):
        raise RuntimeError("alıntı listesi bozuk")
    citations = [str(citation) for citation in raw_citations]
    abstained = bool(body["abstained"])
    raw_retrieved = body.get("retrieved_chunk_ids") or []
    if not isinstance(raw_retrieved, list):
        raise RuntimeError("getirilen parça listesi bozuk")
    retrieved = [str(chunk_id) for chunk_id in raw_retrieved]
    expected = item.get("expected_chunk_id")
    expected_id = expected if isinstance(expected, str) and expected else None
    load_duration_ns = int(body.get("load_duration_ns") or 0)
    prompt_eval_count = int(body.get("prompt_eval_count") or 0)
    prompt_eval_duration_ns = int(body.get("prompt_eval_duration_ns") or 0)
    return {
        "question_id": item["id"],
        "retrieved_chunk_ids": retrieved,
        "expected_chunk_id": expected_id,
        "disclaimer": body["disclaimer"],
        "abstained": abstained,
        "citations": citations,
        "uncited_claim": 0 if abstained or citations else 1,
        "latency_ms": body["latency_ms"],
        "load_duration_ns": load_duration_ns,
        "prompt_eval_count": prompt_eval_count,
        "prompt_eval_duration_ns": prompt_eval_duration_ns,
        "eval_count": eval_count,
        "eval_duration_ns": eval_duration_ns,
        "total_duration_ns": int(body.get("total_duration_ns") or 0),
        "done_reason": done_reason,
        "truncated": generation_truncated(eval_count, num_predict, done_reason),
        "tokens_per_second": tokens_per_second(eval_count, eval_duration_ns),
        "prompt_tokens_per_second": tokens_per_second(prompt_eval_count, prompt_eval_duration_ns),
        "expected_source_retrieved": bool(expected_id) and expected_id in retrieved,
        "expected_source_cited": bool(expected_id) and expected_id in citations,
    }


def load_questions(path: Path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [item for item in payload if item["expect_hit"]]


def profile_records(
    records: list[dict[str, object]],
    *,
    truncation_cap: int | None = None,
) -> dict[str, object]:
    """Önce/sonra kıyası. total_duration eski kayıtta yoksa null kalır.

    truncated alanı varsa o kullanılır. Yoksa truncation_cap ile
    eval_count karşılaştırması yapılır; 512'lik eski tur için bu vekildir.
    """
    count = len(records)
    latencies = [float(record["latency_ms"]) for record in records]
    has_total = all("total_duration_ns" in record for record in records)
    truncated = 0
    for record in records:
        if "truncated" in record:
            truncated += int(bool(record["truncated"]))
        elif truncation_cap is not None and int(record.get("eval_count") or 0) >= truncation_cap:
            truncated += 1
    cited = sum(1 for record in records if record.get("citations"))
    return {
        "count": count,
        "eval_count_sum": sum(int(record.get("eval_count") or 0) for record in records),
        "eval_duration_ns_sum": sum(int(record.get("eval_duration_ns") or 0) for record in records),
        "total_duration_ns_sum": (
            sum(int(record["total_duration_ns"]) for record in records) if has_total else None
        ),
        "citation_rate": cited / count if count else 0.0,
        "abstention_rate": (
            sum(1 for record in records if record.get("abstained")) / count if count else 0.0
        ),
        "truncation_rate": truncated / count if count else 0.0,
        "p50_latency_ms": percentile_nearest(latencies, 0.50),
        "p95_latency_ms": percentile_nearest(latencies, 0.95),
    }


def summarize(records: list[dict[str, object]]) -> dict[str, object]:
    latencies = [float(record["latency_ms"]) for record in records]
    total_tokens = sum(int(record["eval_count"]) for record in records)
    total_ns = sum(int(record["eval_duration_ns"]) for record in records)
    return {
        "count": len(records),
        "uncited_claim_count": sum(int(record["uncited_claim"]) for record in records),
        "disclaimer_present_count": sum(
            1 for record in records if record["disclaimer"] == DISCLAIMER
        ),
        "abstain_count": sum(1 for record in records if record["abstained"]),
        "p95_latency_ms": percentile_95(latencies),
        "tokens_per_second": tokens_per_second(total_tokens, total_ns),
        "p95_method": "nearest_rank",
    }


def run_eval(settings: Settings | None = None) -> dict[str, object]:
    settings = settings or Settings()
    questions = load_questions(settings.questions_path)
    records: list[dict[str, object]] = []
    with TestClient(create_app(settings)) as client:
        client.timeout = httpx.Timeout(settings.request_timeout_seconds + 5)
        for item in questions:
            response = client.post(
                "/v1/chat",
                json={"question": item["question"], "top_k": 3},
            )
            response.raise_for_status()
            records.append(build_record(item, response.json(), settings.num_predict))
    summary = summarize(records)
    summary.update(profile_records(records))
    summary["prompt_tokens_per_second"] = _aggregate_rate(
        records, "prompt_eval_count", "prompt_eval_duration_ns"
    )
    return {
        "model": settings.model,
        "num_ctx": settings.num_ctx,
        "temperature": settings.temperature,
        "top_p": settings.top_p,
        "top_k": settings.top_k,
        "num_predict": settings.num_predict,
        "think": settings.think,
        "ollama_base_url": settings.ollama_base_url,
        "records": records,
        "summary": summary,
    }


def _aggregate_rate(records: list[dict[str, object]], count_key: str, duration_key: str) -> float | None:
    if any(count_key not in record or duration_key not in record for record in records):
        return None
    return tokens_per_second(
        sum(int(record.get(count_key) or 0) for record in records),
        sum(int(record.get(duration_key) or 0) for record in records),
    )


def source_alignment(
    records: list[dict[str, object]],
    questions: list[dict[str, object]],
) -> dict[str, object]:
    """Beklenen parça kimliği alıntıda veya getirilen listede var mı.

    CPU turu getirilen kimlikleri kaydetmediyse retrieval alanı null kalır.
    """
    expected_by_id = {
        str(item["id"]): item.get("expected_chunk_id")
        for item in questions
        if item.get("expect_hit")
    }
    cited = 0
    retrieved = 0
    retrieval_observed = 0
    count = 0
    for record in records:
        question_id = str(record["question_id"])
        if question_id not in expected_by_id:
            continue
        count += 1
        expected = record.get("expected_chunk_id") or expected_by_id[question_id]
        citations = record.get("citations") or []
        if isinstance(expected, str) and expected and expected in citations:
            cited += 1
        if "retrieved_chunk_ids" in record:
            retrieval_observed += 1
            got = record.get("retrieved_chunk_ids") or []
            if isinstance(expected, str) and expected and expected in got:
                retrieved += 1
    return {
        "count": count,
        "expected_source_cited_count": cited,
        "expected_source_retrieved_count": retrieved if retrieval_observed == count and count else None,
    }


def device_view(payload: dict[str, object], questions: list[dict[str, object]]) -> dict[str, object]:
    records = payload["records"]
    if not isinstance(records, list):
        raise RuntimeError("kıyas kayıtları bozuk")
    typed = [record for record in records if isinstance(record, dict)]
    profile = profile_records(typed)
    alignment = source_alignment(typed, questions)
    return {
        "model": payload.get("model"),
        "num_ctx": payload.get("num_ctx"),
        "temperature": payload.get("temperature"),
        "num_predict": payload.get("num_predict"),
        "think": payload.get("think"),
        "p50_latency_ms": profile["p50_latency_ms"],
        "p95_latency_ms": profile["p95_latency_ms"],
        "prompt_tokens_per_second": _aggregate_rate(
            typed, "prompt_eval_count", "prompt_eval_duration_ns"
        ),
        "generation_tokens_per_second": _aggregate_rate(typed, "eval_count", "eval_duration_ns"),
        "citation_rate": profile["citation_rate"],
        "truncation_rate": profile["truncation_rate"],
        "abstention_rate": profile["abstention_rate"],
        **alignment,
    }


CITATION_PRESENCE_NOTE = (
    "Alıntı bulunması klinik doğruluk kanıtlamaz. "
    "Bu sayı yalnızca sentetik derlemdeki beklenen parça kimliğinin "
    "yanıtta görünüp görünmediğini ölçer."
)


def cpu_gpu_comparison(
    cpu_payload: dict[str, object],
    gpu_payload: dict[str, object],
    questions: list[dict[str, object]],
    *,
    cpu_source: str,
    gpu_source: str,
) -> dict[str, object]:
    return {
        "dataset": "data/eval/questions.json expect_hit",
        "synthetic_only": True,
        "citation_presence_note": CITATION_PRESENCE_NOTE,
        "p95_method": "nearest_rank",
        "cpu": {"source": cpu_source, "device": "cpu", **device_view(cpu_payload, questions)},
        "gpu": {"source": gpu_source, "device": "gpu", **device_view(gpu_payload, questions)},
    }


def write_csv(records: list[dict[str, object]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "question_id",
        "retrieved_chunk_ids",
        "expected_chunk_id",
        "abstained",
        "citation_ids",
        "done_reason",
        "latency_ms",
        "load_duration_ns",
        "prompt_eval_count",
        "prompt_eval_duration_ns",
        "eval_count",
        "eval_duration_ns",
        "total_duration_ns",
        "tokens_per_second",
        "prompt_tokens_per_second",
        "truncated",
        "expected_source_retrieved",
        "expected_source_cited",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for record in records:
            retrieved = record.get("retrieved_chunk_ids") or []
            citations = record.get("citations") or []
            writer.writerow(
                {
                    "question_id": record.get("question_id"),
                    "retrieved_chunk_ids": "|".join(str(item) for item in retrieved),
                    "expected_chunk_id": record.get("expected_chunk_id") or "",
                    "abstained": record.get("abstained"),
                    "citation_ids": "|".join(str(item) for item in citations),
                    "done_reason": record.get("done_reason", ""),
                    "latency_ms": record.get("latency_ms"),
                    "load_duration_ns": record.get("load_duration_ns", ""),
                    "prompt_eval_count": record.get("prompt_eval_count", ""),
                    "prompt_eval_duration_ns": record.get("prompt_eval_duration_ns", ""),
                    "eval_count": record.get("eval_count"),
                    "eval_duration_ns": record.get("eval_duration_ns"),
                    "total_duration_ns": record.get("total_duration_ns", ""),
                    "tokens_per_second": record.get("tokens_per_second"),
                    "prompt_tokens_per_second": record.get("prompt_tokens_per_second", ""),
                    "truncated": record.get("truncated", ""),
                    "expected_source_retrieved": record.get("expected_source_retrieved", ""),
                    "expected_source_cited": record.get("expected_source_cited", ""),
                }
            )
    return path


def refuse_baseline_overwrite(output: Path, baseline_dir: Path) -> None:
    """CPU turunun dört rapor dosyası bu koşuda yazma hedefi olamaz."""
    protected = {
        "eval_report.json",
        "eval_report_before.json",
        "latency_comparison.json",
        "smoke_ram.json",
    }
    resolved = output.resolve()
    if resolved.parent == baseline_dir.resolve() and resolved.name in protected:
        raise RuntimeError(f"baseline korunuyor: {resolved}")


def attach_hardware(
    report_path: Path,
    comparison_path: Path,
    hardware: dict[str, object],
) -> None:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["hardware"] = hardware
    report["citation_presence_note"] = CITATION_PRESENCE_NOTE
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if comparison_path.is_file():
        compared = json.loads(comparison_path.read_text(encoding="utf-8"))
        compared["hardware"] = hardware
        compared["citation_presence_note"] = CITATION_PRESENCE_NOTE
        comparison_path.write_text(
            json.dumps(compared, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def write_report(payload: dict[str, object], directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "eval_report.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def snapshot_before(directory: Path) -> Path | None:
    """İlk yeni tur, 512 token'lık raporu üzerine yazmasın."""
    current = directory / "eval_report.json"
    before = directory / "eval_report_before.json"
    if current.is_file() and not before.is_file():
        before.write_bytes(current.read_bytes())
    return before if before.is_file() else None


def comparison_report(before_path: Path, after: dict[str, object]) -> dict[str, object]:
    before_payload = json.loads(before_path.read_text(encoding="utf-8"))
    before_records = before_payload["records"]
    after_records = after["records"]
    if not isinstance(before_records, list) or not isinstance(after_records, list):
        raise RuntimeError("kıyas kayıtları bozuk")
    return {
        "questions": "data/eval/questions.json expect_hit",
        "before": {
            "label": "num_predict=512, think alanı gönderilmedi",
            "source": before_path.name,
            "truncation_rule": "eval_count >= 512",
            **profile_records(before_records, truncation_cap=512),
        },
        "after": {
            "label": f"num_predict={after.get('num_predict')}, think={after.get('think')}",
            "source": "eval_report.json",
            "truncation_rule": "done_reason == length veya eval_count >= num_predict",
            **profile_records(after_records),
        },
    }


def assert_acceptance(payload: dict[str, object]) -> None:
    summary = payload["summary"]
    records = payload["records"]
    if not isinstance(summary, dict) or not isinstance(records, list):
        raise RuntimeError("rapor biçimi bozuk")
    if len(records) != 10:
        raise RuntimeError(f"beklenen 10 kayıt, gelen {len(records)}")
    if int(summary["disclaimer_present_count"]) != 10:
        raise RuntimeError("uyarı metni her kayıtta yok")
    if int(summary["uncited_claim_count"]) != 0:
        raise RuntimeError("alıntısız iddia var")
    if "p95_latency_ms" not in summary or "tokens_per_second" not in summary:
        raise RuntimeError("gecikme özeti yok")
