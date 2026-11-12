"""Geçmiş hastalık araması. GPU çağırmaz."""

from pathlib import Path

from medical_rag.config import Settings
from medical_rag.rag.chunker import load_chunks
from medical_rag.rag.retriever import Bm25Retriever
from medical_rag.safety.policy import ABSTAIN_TEXT, enforce_twin_contract
from medical_rag.twin.clinical_history import parse_history_query
from medical_rag.twin.service import DigitalTwinService


def test_history_cues_select_a_chapter_without_matching_current_metrics() -> None:
    stomach = parse_history_query("daha önce mide rahatsızlığım olmuş mu?")
    assert stomach.active is True
    assert stomach.code_prefixes == ("K2", "K3")

    thyroid = parse_history_query("hipotiroidi tanım daha önce olmuş mu?")
    assert thyroid.active is True
    assert "E0" in thyroid.code_prefixes

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
