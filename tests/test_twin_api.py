import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from medical_rag.config import Settings
from medical_rag.main import create_app
from medical_rag.twin.service import DigitalTwinService
from tests.fakes import FakeOllama


@pytest.fixture(scope="module")
def shared_twin_service(tmp_path_factory: pytest.TempPathFactory) -> DigitalTwinService:
    settings = Settings()
    db_dir = tmp_path_factory.mktemp("g5_api_db")
    service = DigitalTwinService(
        db_path=db_dir / "g5_test.db",
        cco_package_dir=settings.cco_package_dir,
        snomed_package_dir=settings.snomed_package_dir,
        eager_load=True,
    )
    yield service
    service.close()


def test_patients_endpoint_lists_20_cases_without_opaque_ids(
    shared_twin_service: DigitalTwinService,
) -> None:
    fake = FakeOllama()
    app = create_app(ollama=fake, twin=shared_twin_service)
    with TestClient(app) as client:
        resp = client.get("/v1/patients")
    assert resp.status_code == 200
    patients = resp.json()["patients"]
    assert len(patients) == 20
    assert patients[0]["case_id"] == "oracle-pilot-001"
    assert patients[0]["total_rows"] == 1021
    assert patients[18]["case_id"] == "oracle-pilot-019"
    assert patients[18]["has_structured_data"] is False
    assert patients[18]["total_rows"] == 0


def test_emergency_short_circuits_before_model_in_both_modes(
    shared_twin_service: DigitalTwinService,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake = FakeOllama(text="çağrılmamalı")
    app = create_app(ollama=fake, twin=shared_twin_service)
    secret_marker = "gizli-acil-belirti-999"
    question = (
        f"Göğsümde baskı tarzında şiddetli ağrı ve sol koluma yayılan uyuşma var {secret_marker}; "
        "yüzükteki nabzım normal görünüyor, beklemeli miyim?"
    )

    with caplog.at_level(logging.INFO, logger="medical_rag.api"):
        with TestClient(app) as client:
            r_legacy = client.post("/v1/chat", json={"question": question})
            r_twin = client.post(
                "/v1/chat",
                json={"question": question, "case_id": "oracle-pilot-001"},
            )

    assert fake.calls == 0
    for resp in (r_legacy, r_twin):
        body = resp.json()
        assert resp.status_code == 200
        assert body["emergency"] is True
        assert body["intent"] == "emergency"
        assert body["eval_count"] == 0
        assert "112" in body["answer"]
    assert secret_marker not in caplog.text


def test_twin_symptom_chat_uses_three_layers_and_hides_question_in_logs(
    shared_twin_service: DigitalTwinService,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake = FakeOllama(
        text=(
            "Son ana uykunuz 483 dakika olarak kayıtlıdır [CCO:oracle-pilot-001:F777]. "
            "Baş ağrısı bulgusu SNOMED CT'de 25064002 kavramıyla tanımlanır [SNOMED:25064002] "
            "ve uyku döngüsü genel sözlükte açıklanmıştır [GENEL:uyku-0]."
        )
    )
    app = create_app(ollama=fake, twin=shared_twin_service)
    marker = "gizli-hasta-sorusu-abc"

    with caplog.at_level(logging.INFO, logger="medical_rag.api"):
        with TestClient(app) as client:
            resp = client.post(
                "/v1/chat",
                json={
                    "question": (
                        f"Başım ağrıyor {marker}; son uyku düzenim ve kalp ölçümlerim "
                        "açısından kişisel kayıtlarımda ne var?"
                    ),
                    "case_id": "oracle-pilot-001",
                    "top_k": 3,
                },
            )

    assert resp.status_code == 200
    body = resp.json()
    assert fake.calls == 1
    assert fake.last_num_ctx == 4096
    assert fake.last_num_predict == 384
    assert body["abstained"] is False
    assert body["case_id"] == "oracle-pilot-001"
    assert body["intent"] == "patient_symptom_twin"
    assert "CCO:oracle-pilot-001:F777" in body["citations"]
    assert "SNOMED:25064002" in body["citations"]
    assert len(body["evidence_layers"]["patient_cco"]) >= 1
    assert any(
        item["citation_id"] == "SNOMED:25064002"
        for item in body["evidence_layers"]["snomed_terminology"]
    )
    assert len(body["evidence_layers"]["general_knowledge"]) >= 1
    assert marker not in caplog.text


def test_unknown_or_malformed_case_id_handling(
    shared_twin_service: DigitalTwinService,
) -> None:
    fake = FakeOllama()
    app = create_app(ollama=fake, twin=shared_twin_service)
    with TestClient(app) as client:
        bad_format = client.post(
            "/v1/chat",
            json={"question": "Son uykum kaç dakika?", "case_id": "hasta-1"},
        )
        missing_case = client.post(
            "/v1/chat",
            json={"question": "Son uykum kaç dakika?", "case_id": "oracle-pilot-999"},
        )
    assert bad_format.status_code == 422
    assert missing_case.status_code == 404
    assert fake.calls == 0


@pytest.mark.ollama
def test_live_three_patient_questions_on_26b() -> None:
    """SSH tüneli (127.0.0.1:11435) açıkken ilk 3 hasta sorusunu canlı doğrular."""
    import json

    settings = Settings(
        ollama_base_url="http://127.0.0.1:11435",
        model="gemma4:26b-a4b-it-q4_K_M",
    )
    app = create_app(settings=settings)
    questions = [
        (
            "q1_exact_sleep_hrv",
            "oracle-pilot-001",
            "Son ana uykum kaç dakika sürdü, 7 günlük uyku ortalamam nedir ve "
            "günlük HRV kişisel bazal değerim neden görünmüyor?",
        ),
        (
            "q2_symptom_snomed_cco",
            "oracle-pilot-001",
            "Başım ağrıyor; kişisel kayıtlarımda son uyku düzenim, kalp/HRV ölçümlerim "
            "veya kayıtlı tanı ve ilaçlarım açısından hangi veriler var?",
        ),
        (
            "q3_emergency_precheck",
            "oracle-pilot-001",
            "Göğsümde baskı tarzında şiddetli ağrı, sol koluma yayılan uyuşma ve nefes darlığı başladı; "
            "yüzükteki nabzım normal görünüyor, beklemeli miyim?",
        ),
    ]

    telemetry_summary = []
    with TestClient(app) as client:
        health_resp = client.get("/health").json()
        assert health_resp["ollama"] == "ok", "127.0.0.1:11435 SSH tüneli kapalı veya Ollama erişilemez"

        for q_id, case_id, text in questions:
            resp = client.post(
                "/v1/chat",
                json={"question": text, "case_id": case_id, "top_k": 3},
            )
            assert resp.status_code == 200
            body = resp.json()
            if q_id == "q3_emergency_precheck":
                assert body["emergency"] is True
                assert body["eval_count"] == 0
                assert "112" in body["answer"]
            else:
                assert body["abstained"] is False
                assert len(body["citations"]) >= 1
            # Ham yanıt veya hasta değeri diske yazılmaz; yalnız anonim telemetri özeti kaydedilir
            telemetry_summary.append(
                {
                    "id": q_id,
                    "intent": body["intent"],
                    "emergency": body["emergency"],
                    "abstained": body["abstained"],
                    "citation_count": len(body["citations"]),
                    "latency_ms": round(body["latency_ms"], 1),
                    "eval_count": body["eval_count"],
                    "prompt_eval_count": body["prompt_eval_count"],
                }
            )

    out_dir = settings.runtime_dir / "g5-v1"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "three_questions_telemetry.json").write_text(
        json.dumps(telemetry_summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
