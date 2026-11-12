"""Geçmiş hastalık araması. GPU çağırmaz."""

from pathlib import Path

from medical_rag.config import Settings
from medical_rag.rag.chunker import load_chunks
from medical_rag.rag.retriever import Bm25Retriever
from types import SimpleNamespace

from medical_rag.safety.policy import ABSTAIN_TEXT, enforce_twin_contract
from medical_rag.twin.clinical_history import (
    classify_history_search,
    compose_coded_history_answer,
    parse_history_query,
)
from medical_rag.twin.service import DigitalTwinService


def test_history_cues_select_a_chapter_without_matching_current_metrics() -> None:
    stomach = parse_history_query("daha önce mide rahatsızlığım olmuş mu?")
    assert stomach.active is True
    assert stomach.code_prefixes == ("K2", "K3")

    thyroid = parse_history_query("hipotiroidi tanım daha önce olmuş mu?")
    assert thyroid.active is True
    assert "E0" in thyroid.code_prefixes
    assert thyroid.concepts[0].concept_id == "40930008"
    assert all(concept.concept_id != "14304000" for concept in thyroid.concepts)

    gland = parse_history_query("geçmişimde tiroit hastalığı var mı?")
    assert gland.resolved is True
    assert gland.code_prefixes == ("E0",)
    assert gland.concepts[0].concept_id == "14304000"
    assert classify_history_search(gland, 0) == "NO_MATCH"
    assert classify_history_search(gland, 1) == "MATCH"

    heart = parse_history_query("daha önce kalp rahatsızlığım olmuş mu?")
    assert heart.concepts[0].concept_id == "56265001"
    for prefix in ("I01", "I05", "I06", "I07", "I08", "I09", "I1", "I2", "I3", "I4", "I5"):
        assert prefix in heart.code_prefixes
    assert "I6" not in heart.code_prefixes

    unknown = parse_history_query("daha önce fil hastalığı geçirdim mi?")
    assert unknown.active is True
    assert unknown.resolved is False
    assert classify_history_search(unknown, 0) == "UNRESOLVED"

    assert parse_history_query("başım ağrıyor.").active is False
    assert parse_history_query("son ana uykum kaç dakika sürdü?").active is False


def test_history_search_keeps_old_coded_diagnoses_in_the_prompt(tmp_path: Path) -> None:
    settings = Settings()
    chunks = load_chunks(settings.corpus_dir, settings.chunk_size, settings.chunk_overlap)
    retriever = Bm25Retriever(chunks, settings.bm25_score_threshold)
    twin = DigitalTwinService(
        db_path=tmp_path / "history.db",
        cco_package_dir=settings.cco_package_dir,
        snomed_package_dir=settings.snomed_package_dir,
        eager_load=True,
    )
    try:
        prepared = twin.prepare_turn(
            "Daha önce mide rahatsızlığım olmuş mu?",
            case_id="oracle-pilot-006",
            retriever=retriever,
        )
        assert prepared.plan.intent == "clinical_history_search"
        rendered = prepared.rendered_context
        for alias in ("F272", "F268", "F271", "F270", "F269"):
            assert f"CCO:oracle-pilot-006:{alias}" in rendered
        assert "HISTORY-EMPTY" not in rendered
        assert "definitive-count" not in rendered

        thyroid = twin.prepare_turn(
            "Hipotiroidi tanım daha önce olmuş mu?",
            case_id="oracle-pilot-018",
            retriever=retriever,
        )
        assert thyroid.plan.intent == "clinical_history_search"
        assert "E03" in thyroid.rendered_context
        assert "HISTORY-EMPTY" not in thyroid.rendered_context

        gland_positive = twin.prepare_turn(
            "Geçmişimde tiroit hastalığı var mı?",
            case_id="oracle-pilot-018",
            retriever=retriever,
        )
        positive_text = gland_positive.rendered_context
        assert gland_positive.plan.history_concepts[0][0] == "14304000"
        assert "MATCH" in positive_text
        assert "E03" in positive_text
        assert "F442" in positive_text
        assert "preliminary" in positive_text
        assert "ön tanı" in gland_positive.history_answer
        assert "kesin tanı" not in gland_positive.history_answer
        assert "E03" in gland_positive.history_answer
        assert "F442" in gland_positive.history_answer
        positive_decision = enforce_twin_contract(
            gland_positive.history_answer,
            gland_positive.evidence.allowed_citation_ids,
        )
        assert positive_decision.abstained is False
        assert "CCO:oracle-pilot-018:F442" in positive_decision.citations
        assert "HISTORY-EMPTY" not in positive_text
        assert "R11" not in positive_text
        assert "J06" not in positive_text

        gland_negative = twin.prepare_turn(
            "Geçmişimde tiroit hastalığı var mı?",
            case_id="oracle-pilot-006",
            retriever=retriever,
        )
        negative_text = gland_negative.rendered_context
        assert "NO_MATCH" in negative_text
        assert "CCO:oracle-pilot-006:HISTORY-EMPTY" in negative_text
        assert "14304000" in negative_text
        assert "F272" not in negative_text
        assert "K29" not in negative_text
        assert "HISTORY-UNRESOLVED" not in negative_text

        heart = twin.prepare_turn(
            "Daha önce kalp rahatsızlığım olmuş mu?",
            case_id="oracle-pilot-006",
            retriever=retriever,
        )
        assert heart.plan.history_concepts[0][0] == "56265001"
        assert "I05" in heart.plan.history_prefixes
        assert "CCO:oracle-pilot-006:HISTORY-EMPTY" in heart.rendered_context
        assert "F272" not in heart.rendered_context

        unresolved = twin.prepare_turn(
            "Daha önce fil hastalığı geçirdim mi?",
            case_id="oracle-pilot-006",
            retriever=retriever,
        )
        assert unresolved.plan.history_prefixes == ()
        assert "CCO:oracle-pilot-006:HISTORY-UNRESOLVED" in unresolved.rendered_context
        assert "HISTORY-EMPTY" not in unresolved.rendered_context
        assert "F272" not in unresolved.rendered_context
        assert "K29" not in unresolved.rendered_context

        empty = twin.prepare_turn(
            "Daha önce astım geçirdim mi?",
            case_id="oracle-pilot-019",
            retriever=retriever,
        )
        assert "CCO:oracle-pilot-019:HISTORY-EMPTY" in empty.rendered_context
    finally:
        twin.close()


def test_history_validator_rejects_absence_that_cites_only_a_count() -> None:
    allowed = [
        "CCO:oracle-pilot-006:HISTORY-SCOPE",
        "CCO:oracle-pilot-006:F268",
        "CCO:oracle-pilot-006:F269",
        "GENEL:sindirim-0",
    ]
    denied = enforce_twin_contract(
        "Mide tanısı bulunmamaktadır [CCO:oracle-pilot-006:HISTORY-SCOPE] [GENEL:sindirim-0].",
        allowed,
    )
    assert denied.abstained is True
    assert denied.answer == ABSTAIN_TEXT

    cited = enforce_twin_contract(
        "Kayıtlı özofajit satırı vardır [CCO:oracle-pilot-006:F268].",
        allowed,
    )
    assert cited.abstained is False
    assert "CCO:oracle-pilot-006:F268" in cited.citations

    empty_allowed = [
        "CCO:oracle-pilot-019:HISTORY-SCOPE",
        "CCO:oracle-pilot-019:HISTORY-EMPTY",
    ]
    empty_answer = enforce_twin_contract(
        "Bu aramada kodlu tanı bulunmamaktadır [CCO:oracle-pilot-019:HISTORY-EMPTY].",
        empty_allowed,
    )
    assert empty_answer.abstained is False


def test_doctor_referral_does_not_block_a_cited_history_answer() -> None:
    allowed = [
        "CCO:oracle-pilot-018:HISTORY-SCOPE",
        "CCO:oracle-pilot-018:F442",
        "SNOMED:14304000",
    ]
    raw = (
        'Kayıtlarınıza göre, 2026-04-08 tarihinde "Hipotiroidizm, diğer (icd-10:E03)" '
        "tanısı [CCO:oracle-pilot-018:F442] yer almaktadır. "
        "Tanının güncel durumunu doktorunuza danışmalısınız."
    )
    decision = enforce_twin_contract(raw, allowed)
    assert decision.abstained is False
    assert "CCO:oracle-pilot-018:F442" in decision.citations

    role = enforce_twin_contract(
        "[SNOMED:14304000] Doktorunuz olarak tanınız migrendir.",
        allowed,
    )
    assert role.abstained is True

    identity = enforce_twin_contract(
        "[CCO:oracle-pilot-018:F442] Ben doktorunuzum.",
        allowed,
    )
    assert identity.abstained is True


def test_history_answer_keeps_preliminary_distinct_from_confirmed() -> None:
    preliminary = compose_coded_history_answer(
        case_id="oracle-pilot-018",
        status="MATCH",
        coded_facts=[
            SimpleNamespace(
                code="E03",
                display_text="Hipotiroidizm, diğer",
                clinical_attributes={"type": "preliminary"},
                occurred_from="2026-04-08T10:58:00+03:00",
                fact_alias="F442",
            )
        ],
    )
    assert "Durum: ön tanı" in preliminary
    assert "kesin tanı" not in preliminary
    assert "[CCO:oracle-pilot-018:F442]" in preliminary

    confirmed = compose_coded_history_answer(
        case_id="oracle-pilot-006",
        status="MATCH",
        coded_facts=[
            SimpleNamespace(
                code="K29.6",
                display_text="Gastritler, diğer",
                clinical_attributes={"type": "confirmed"},
                occurred_from="2024-04-19T00:00:00+03:00",
                fact_alias="F272",
            )
        ],
    )
    assert "Durum: kesin tanı" in confirmed
    assert "ön tanı" not in confirmed

    empty = compose_coded_history_answer(
        case_id="oracle-pilot-006",
        status="NO_MATCH",
        coded_facts=[],
    )
    assert "[CCO:oracle-pilot-006:HISTORY-EMPTY]" in empty


def test_exact_sleep_question_stays_on_the_metric_path(tmp_path: Path) -> None:
    settings = Settings()
    chunks = load_chunks(settings.corpus_dir, settings.chunk_size, settings.chunk_overlap)
    retriever = Bm25Retriever(chunks, settings.bm25_score_threshold)
    twin = DigitalTwinService(
        db_path=tmp_path / "sleep.db",
        cco_package_dir=settings.cco_package_dir,
        snomed_package_dir=settings.snomed_package_dir,
        eager_load=True,
    )
    try:
        prepared = twin.prepare_turn(
            "Son ana uykum kaç dakika sürdü?",
            case_id="oracle-pilot-001",
            retriever=retriever,
        )
        assert prepared.plan.intent != "clinical_history_search"
        assert "HISTORY-SCOPE" not in prepared.rendered_context
    finally:
        twin.close()
