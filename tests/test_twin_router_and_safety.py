import json
from pathlib import Path

from medical_rag.config import Settings
from medical_rag.rag.chunker import load_chunks
from medical_rag.rag.retriever import Bm25Retriever
from medical_rag.safety.emergency import EMERGENCY_TEXT, check_emergency
from medical_rag.safety.policy import ABSTAIN_TEXT, enforce_twin_contract
from medical_rag.twin.service import DigitalTwinService


def test_emergency_precheck_catches_red_flags_and_ignores_benign_queries() -> None:
    red_flag = check_emergency(
        "Göğsümde baskı tarzında şiddetli ağrı, sol koluma yayılan uyuşma ve nefes darlığı başladı; "
        "yüzükteki nabzım normal görünüyor, beklemeli miyim?"
    )
    assert red_flag.is_emergency is True
    assert red_flag.category == "acute_chest_coronary"
    assert "112" in red_flag.message
    assert red_flag.message == EMERGENCY_TEXT

    stroke = check_emergency("Yüzümde kayma oldu ve konuşmam bozuldu, ne yapmalıyım?")
    assert stroke.is_emergency is True
    assert stroke.category == "acute_stroke_neuro"

    # Baseline 12 eval questions must NEVER trigger emergency false-positives
    settings = Settings()
    eval_cases = json.loads(settings.questions_path.read_text(encoding="utf-8"))
    for case in eval_cases:
        decision = check_emergency(case["question"])
        assert decision.is_emergency is False, case["id"]

    # Non-emergency symptom query must pass emergency pre-check
    headache = check_emergency(
        "Başım ağrıyor; kişisel kayıtlarımda uyku ve kalp ölçümlerim açısından ne var?"
    )
    assert headache.is_emergency is False


def test_three_layer_evidence_separation_and_empty_profile_handling(tmp_path: Path) -> None:
    settings = Settings()
    chunks = load_chunks(settings.corpus_dir, settings.chunk_size, settings.chunk_overlap)
    retriever = Bm25Retriever(chunks, settings.bm25_score_threshold)

    twin = DigitalTwinService(
        db_path=tmp_path / "test_g5.db",
        cco_package_dir=settings.cco_package_dir,
        snomed_package_dir=settings.snomed_package_dir,
    )
    try:
        # Question 1: Exact sleep & missing HRV baseline on oracle-pilot-001
        q1 = twin.prepare_turn(
            "Son ana uykum kaç dakika sürdü, 7 günlük uyku ortalamam nedir ve "
            "günlük HRV kişisel bazal değerim neden görünmüyor?",
            case_id="oracle-pilot-001",
            retriever=retriever,
        )
        assert q1.plan.intent in {"patient_exact_query", "patient_symptom_twin"}
        assert any(
            "sleep.duration.last-main-sleep" in item.title
            for item in q1.evidence.patient_cco
        )
        assert any(
            "sleep.duration.7d-average" in item.title
            for item in q1.evidence.patient_cco
        )
        assert any(
            item.citation_id.startswith("CCO:oracle-pilot-001:MISSING-cardio-hrv-personal-baseline")
            for item in q1.evidence.patient_cco
        )
        assert len(q1.rendered_context) <= 7500

        # Question 2: Symptom headache + personal CCO + general dictionary layers separated
        q2 = twin.prepare_turn(
            "Başım ağrıyor; kişisel kayıtlarımda son uyku düzenim ve kalp ölçümlerim açısından ne var?",
            case_id="oracle-pilot-001",
            retriever=retriever,
        )
        assert q2.plan.intent == "patient_symptom_twin"
        assert any(item.citation_id.startswith("CCO:oracle-pilot-001:") for item in q2.evidence.patient_cco)
        assert any(item.citation_id == "SNOMED:25064002" for item in q2.evidence.snomed_terminology)
        assert any(item.citation_id.startswith("GENEL:") for item in q2.evidence.general_knowledge)
        assert "=== KATMAN 1: HASTA KİŞİSEL CCO KAYITLARI" in q2.rendered_context
        assert "=== KATMAN 2: SNOMED CT IPS TERMİNOLOJİ BİLGİSİ" in q2.rendered_context
        assert "=== KATMAN 3: GENEL KLİNİK EĞİTİM SÖZLÜĞÜ" in q2.rendered_context

        # Empty profile (oracle-pilot-019): 0 structured facts must produce explicit EMPTY marker
        empty_turn = twin.prepare_turn(
            "Kayıtlarımda son uyku ve tahlil değerlerim nedir?",
            case_id="oracle-pilot-019",
            retriever=retriever,
        )
        assert any(
            item.citation_id == "CCO:oracle-pilot-019:EMPTY"
            for item in empty_turn.evidence.patient_cco
        )

        # Out-of-scope question even with case_id must route to out_of_scope
        weather_turn = twin.prepare_turn(
            "İstanbul'da yarın hava durumu nasıl olacak?",
            case_id="oracle-pilot-001",
            retriever=retriever,
        )
        assert weather_turn.plan.intent == "out_of_scope"
    finally:
        twin.close()


def test_twin_contract_allows_cited_patient_labs_but_blocks_prescribing_or_uncited() -> None:
    allowed = ["CCO:oracle-pilot-001:F10", "SNOMED:25064002", "GENEL:uyku-0"]

    # Factual patient lab value in mg/dL with valid citation -> allowed
    valid = enforce_twin_contract(
        "Kayıtlı açlık glukoz ölçümünüz 94 mg/dL olarak görünmektedir [CCO:oracle-pilot-001:F10] "
        "ve baş ağrısı bulgusu SNOMED'de 25064002 koduyla tanımlanır [SNOMED:25064002].",
        allowed,
    )
    assert valid.abstained is False
    assert valid.citations == ["CCO:oracle-pilot-001:F10", "SNOMED:25064002"]

    # Uncited output -> abstains
    uncited = enforce_twin_contract("Son uykunuz 420 dakikadır.", allowed)
    assert uncited.abstained is True
    assert uncited.answer == ABSTAIN_TEXT

    # Doctor role or dosage instruction -> abstains
    dosage_advice = enforce_twin_contract(
        "[CCO:oracle-pilot-001:F10] Baş ağrınız için 500 mg alın.",
        allowed,
    )
    assert dosage_advice.abstained is True

    clinician_claim = enforce_twin_contract(
        "[SNOMED:25064002] Doktorunuz olarak tanınız migrendir.",
        allowed,
    )
    assert clinician_claim.abstained is True
