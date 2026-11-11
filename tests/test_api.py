import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from medical_rag.config import Settings
from medical_rag.llm.ollama_client import OllamaHTTPError, OllamaTimeout
from medical_rag.main import create_app
from medical_rag.rag.retriever import ScoredChunk
from medical_rag.safety.policy import ABSTAIN_TEXT, DISCLAIMER
from tests.fakes import FakeOllama, ScriptedRetriever

HIT = ScoredChunk(id="kan-basinci-0", text="Sistolik eğitim cümlesi.", source="kan-basinci.md", score=3.0)


def test_ollama_client_exists_without_waiting_for_lifespan() -> None:
    app = create_app()
    assert app.state.ollama is not None


def test_health_ok_and_degraded() -> None:
    alive = FakeOllama(healthy=True)
    with TestClient(create_app(ollama=alive)) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["ollama"] == "ok"
    assert response.json()["model"] == "gemma4:e4b"

    dead = FakeOllama(healthy=False)
    with TestClient(create_app(ollama=dead)) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["ollama"] == "unreachable"


def test_below_threshold_does_not_call_model() -> None:
    fake = FakeOllama(text="çağrılmamalı")
    app = create_app(ollama=fake, retriever=ScriptedRetriever([]))
    with TestClient(app) as client:
        response = client.post("/v1/chat", json={"question": "Bu soru eşik altında."})
    body = response.json()
    assert response.status_code == 200
    assert fake.calls == 0
    assert body["abstained"] is True
    assert body["answer"] == ABSTAIN_TEXT
    assert body["citations"] == []
    assert body["disclaimer"] == DISCLAIMER


def test_cited_answer_keeps_chunk_id() -> None:
    fake = FakeOllama(text="Sistolik kasılmayı anlatır [kan-basinci-0].")
    app = create_app(ollama=fake, retriever=ScriptedRetriever([HIT]))
    with TestClient(app) as client:
        response = client.post("/v1/chat", json={"question": "Sistolik basınç nedir?"})
    body = response.json()
    assert fake.calls == 1
    assert body["abstained"] is False
    assert "kan-basinci-0" in body["answer"]
    assert body["citations"] == ["kan-basinci-0"]
    assert body["retrieved_chunk_ids"] == ["kan-basinci-0"]
    assert body["disclaimer"] == DISCLAIMER


def test_chat_copies_prompt_timings() -> None:
    fake = FakeOllama(
        text="Sistolik kasılmayı anlatır [kan-basinci-0].",
        load_duration_ns=11,
        prompt_eval_count=40,
        prompt_eval_duration_ns=4_000_000_000,
    )
    app = create_app(ollama=fake, retriever=ScriptedRetriever([HIT]))
    with TestClient(app) as client:
        body = client.post("/v1/chat", json={"question": "Sistolik basınç nedir?"}).json()
    assert body["load_duration_ns"] == 11
    assert body["prompt_eval_count"] == 40
    assert body["prompt_eval_duration_ns"] == 4_000_000_000
    assert body["retrieved_chunk_ids"] == ["kan-basinci-0"]


def test_missing_citation_becomes_abstain() -> None:
    fake = FakeOllama(text="Bunu bağlam olmadan uydurdum.")
    app = create_app(ollama=fake, retriever=ScriptedRetriever([HIT]))
    with TestClient(app) as client:
        response = client.post("/v1/chat", json={"question": "Sistolik basınç nedir?"})
    body = response.json()
    assert fake.calls == 1
    assert body["abstained"] is True
    assert body["answer"] == ABSTAIN_TEXT
    assert "kan-basinci-0" not in body["answer"]


def test_doctor_role_becomes_abstain() -> None:
    fake = FakeOllama(text="[kan-basinci-0] Doktorunuz olarak tanınız yüksek tansiyon.")
    app = create_app(ollama=fake, retriever=ScriptedRetriever([HIT]))
    with TestClient(app) as client:
        response = client.post("/v1/chat", json={"question": "Sistolik basınç nedir?"})
    assert response.json()["abstained"] is True
    assert response.json()["answer"] == ABSTAIN_TEXT


def test_real_corpus_negative_question_skips_model() -> None:
    fake = FakeOllama(text="çağrılmamalı")
    with TestClient(create_app(ollama=fake)) as client:
        response = client.post(
            "/v1/chat",
            json={"question": "İstanbul'da yarın hava durumu nasıl olacak?"},
        )
    assert response.status_code == 200
    assert fake.calls == 0
    assert response.json()["abstained"] is True


def test_complete_reports_num_ctx() -> None:
    fake = FakeOllama(text="Sentetik duman testi basarili.")
    with TestClient(create_app(ollama=fake)) as client:
        response = client.post(
            "/v1/complete",
            json={"prompt": "Yanıt olarak yalnızca şu cümleyi yaz: Sentetik duman testi basarili."},
        )
    body = response.json()
    assert response.status_code == 200
    assert body["num_ctx"] == 2048
    assert body["text"]
    assert fake.last_num_predict == Settings().smoke_num_predict


def test_model_errors_hide_the_question() -> None:
    question = "Sistolik basınç gizli-soru-kodu"
    app = create_app(ollama=FakeOllama(fail=OllamaTimeout()), retriever=ScriptedRetriever([HIT]))
    with TestClient(app) as client:
        timed_out = client.post("/v1/chat", json={"question": question})
    assert timed_out.status_code == 504
    assert "gizli-soru-kodu" not in timed_out.text

    app = create_app(
        ollama=FakeOllama(fail=OllamaHTTPError(500)),
        retriever=ScriptedRetriever([HIT]),
    )
    with TestClient(app) as client:
        failed = client.post("/v1/chat", json={"question": question})
    assert failed.status_code == 503
    assert "gizli-soru-kodu" not in failed.text


def test_chat_log_omits_question(caplog: pytest.LogCaptureFixture) -> None:
    marker = "gizli-soru-ifadesi-xyz"
    fake = FakeOllama(text="Sistolik kasılmayı anlatır [kan-basinci-0].")
    app = create_app(ollama=fake, retriever=ScriptedRetriever([HIT]))
    with caplog.at_level(logging.INFO, logger="medical_rag.api"):
        with TestClient(app) as client:
            client.post("/v1/chat", json={"question": f"Sistolik basınç {marker}"})
    assert marker not in caplog.text


def test_blank_and_long_question_rejected() -> None:
    fake = FakeOllama()
    with TestClient(create_app(ollama=fake, retriever=ScriptedRetriever([]))) as client:
        blank = client.post("/v1/chat", json={"question": "   "})
        huge = client.post("/v1/chat", json={"question": "a" * 501})
    assert blank.status_code == 422
    assert huge.status_code == 422
    assert fake.calls == 0


def test_generation_defaults_stay_bounded() -> None:
    settings = Settings()
    assert settings.num_ctx == 2048
    assert settings.temperature == 0.2
    assert settings.num_predict == 128
    assert settings.think is False


def test_loopback_is_required() -> None:
    with pytest.raises(ValueError):
        Settings(ollama_base_url="http://0.0.0.0:11434")


@pytest.mark.ollama
def test_live_smoke_records_memory() -> None:
    from medical_rag.eval.smoke import run_smoke, write_smoke

    settings = Settings()
    payload = run_smoke(settings)
    write_smoke(payload, settings.runtime_dir)
    assert payload["num_ctx"] == 2048
    assert int(payload["sample_count"]) >= 1
    assert int(payload["peak_used_physical_bytes"]) > 0
    assert payload["text_nonempty"] is True
    assert float(payload["elapsed_seconds"]) <= settings.request_timeout_seconds
    assert payload["within_memory_limit"] is True
