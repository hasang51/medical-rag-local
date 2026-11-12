"""Geçmiş hastalık araması. GPU çağırmaz."""

from pathlib import Path

from medical_rag.config import Settings
from medical_rag.rag.chunker import load_chunks
from medical_rag.rag.retriever import Bm25Retriever
from types import SimpleNamespace

from medical_rag.safety.policy import ABSTAIN_TEXT, enforce_twin_contract
from medical_rag.rag.retriever import ScoredChunk
from medical_rag.twin.cco_adapter import AdaptedFact, AdaptedPatientBundle
from medical_rag.twin.clinical_history import (
    classify_history_search,
    compose_coded_history_answer,
    parse_history_query,
    select_supporting_facts,
)
from medical_rag.twin.evidence_builder import EvidenceBuilder
from medical_rag.twin.service import DigitalTwinService
from tests.fakes import FakeOllama, ScriptedRetriever


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
        positive_ids = [item.citation_id for item in gland_positive.evidence.patient_cco]
        assert "CCO:oracle-pilot-018:F499" not in positive_ids
        assert "CCO:oracle-pilot-018:F1105" not in positive_ids
        assert gland_positive.evidence.general_knowledge == []

        hypo_ids = [item.citation_id for item in thyroid.evidence.patient_cco]
        assert "CCO:oracle-pilot-018:F442" in hypo_ids
        assert "CCO:oracle-pilot-018:F499" not in hypo_ids
        assert "CCO:oracle-pilot-018:F1105" not in hypo_ids
        assert thyroid.evidence.general_knowledge == []
        assert "GENEL:bagisiklik-0" not in thyroid.evidence.allowed_citation_ids

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


def _fact(**overrides: object) -> AdaptedFact:
    base: dict[str, object] = {
        "case_id": "oracle-pilot-018",
        "fact_alias": "F1",
        "source_index": 1,
        "family": "diagnosis",
        "collection_kind": "facts",
        "definition": "diagnosis.recorded-item|1",
        "canonical_id": "diagnosis.recorded-item",
        "definition_version": "1",
        "evaluation_key": "code:icd-10:E03",
        "evaluation_status": "success",
        "value_type": "coded",
        "amount": None,
        "unit": None,
        "code_system": "icd-10",
        "code": "E03",
        "display_text": "Hipotiroidizm, diğer",
        "narrative_sections": {},
        "clinical_attributes": {"type": "preliminary", "visitDate": "2026-04-08"},
        "truncated": False,
        "occurred_from": "2026-04-08T10:58:00+03:00",
        "occurred_to": "2026-04-08T10:58:00+03:00",
        "recorded_at": "2026-04-08T11:00:00+03:00",
        "valid_from": "2026-04-08T10:58:00+03:00",
        "valid_until": None,
        "export_status": "active",
        "superseded_at": None,
        "supersedes_fact_alias": None,
        "supersede_reason": None,
        "engine_version": "1",
        "missing_reasons": [],
        "source_issues": [],
        "evidence": [],
        "comparisons": [],
    }
    base.update(overrides)
    return AdaptedFact(**base)  # type: ignore[arg-type]


def test_same_day_visit_is_not_enough_to_support_a_coded_diagnosis() -> None:
    diagnosis = _fact(fact_alias="F442")
    abdomen = _fact(
        fact_alias="F499",
        family="imaging",
        canonical_id="imaging.recorded-item",
        definition="imaging.recorded-item|1",
        value_type="narrative",
        code_system=None,
        code=None,
        display_text="Üst abdomen ultrasonografisi",
        clinical_attributes={"examName": "Üst abdomen ultrasonografisi", "visitDate": "2026-04-08"},
    )
    visit_note = _fact(
        fact_alias="F1105",
        family="visit",
        canonical_id="visit.examination",
        definition="visit.examination|1",
        value_type="narrative",
        code_system=None,
        code=None,
        display_text="Poliklinik muayene notu",
        narrative_sections={"not": "Aynı vizit. Karın muayenesi olağan. Ek yakınma yok."},
        clinical_attributes={"visitDate": "2026-04-08"},
    )
    thyroid_scan = _fact(
        fact_alias="F500",
        family="imaging",
        canonical_id="imaging.recorded-item",
        definition="imaging.recorded-item|1",
        value_type="narrative",
        code_system=None,
        code=None,
        display_text="Tiroid ultrasonografisi",
        clinical_attributes={"examName": "Tiroid ultrasonografisi"},
        occurred_from="2025-01-02T09:00:00+03:00",
        occurred_to="2025-01-02T09:00:00+03:00",
    )
    tsh = _fact(
        fact_alias="F501",
        family="lab",
        canonical_id="lab.tsh",
        definition="lab.tsh|1",
        value_type="quantity",
        code_system=None,
        code=None,
        display_text="TSH",
        amount=6.2,
        unit="mIU/L",
        occurred_from="2025-11-01T08:00:00+03:00",
        occurred_to="2025-11-01T08:00:00+03:00",
    )
    concepts = parse_history_query("hipotiroidi tanısı daha önce olmuş mu?").concepts
    selected = select_supporting_facts(
        [abdomen, visit_note, thyroid_scan, tsh],
        concepts,
        coded_facts=[diagnosis],
    )
    aliases = [fact.fact_alias for fact in selected]
    assert aliases == ["F500", "F501"]
    assert select_supporting_facts(
        [abdomen, visit_note],
        concepts,
        coded_facts=[],
    ) == []


def test_history_sources_keep_coded_diagnosis_and_real_support(tmp_path: Path) -> None:
    bundle = AdaptedPatientBundle(
        case_id="oracle-pilot-018",
        subject_fingerprint="synthetic",
        evaluated_at="2026-11-01T00:00:00+03:00",
        exported_at="2026-11-01T00:00:00+03:00",
        cco_as_of="2026-11-01T00:00:00+03:00",
        export_scope="test",
        has_structured_data=True,
        total_rows=4,
        value_fact_count=4,
        missing_result_count=0,
        families=["diagnosis", "imaging", "visit", "lab"],
        facts=[
            _fact(fact_alias="F442", source_index=442),
            _fact(
                fact_alias="F499",
                source_index=499,
                family="imaging",
                canonical_id="imaging.recorded-item",
                definition="imaging.recorded-item|1",
                value_type="narrative",
                code_system=None,
                code=None,
                display_text="Üst abdomen ultrasonografisi",
                clinical_attributes={
                    "examName": "Üst abdomen ultrasonografisi",
                    "visitDate": "2026-04-08",
                },
            ),
            _fact(
                fact_alias="F1105",
                source_index=1105,
                family="visit",
                canonical_id="visit.examination",
                definition="visit.examination|1",
                value_type="narrative",
                code_system=None,
                code=None,
                display_text="Poliklinik muayene notu",
                narrative_sections={"not": "Aynı vizit. Karın muayenesi olağan. Ek yakınma yok."},
                clinical_attributes={"visitDate": "2026-04-08"},
            ),
            _fact(
                fact_alias="F500",
                source_index=500,
                family="imaging",
                canonical_id="imaging.recorded-item",
                definition="imaging.recorded-item|1",
                value_type="narrative",
                code_system=None,
                code=None,
                display_text="Tiroid ultrasonografisi",
                clinical_attributes={"examName": "Tiroid ultrasonografisi"},
                occurred_from="2025-01-02T09:00:00+03:00",
                occurred_to="2025-01-02T09:00:00+03:00",
            ),
        ],
        glossary=[],
        narrative_sections=[],
    )
    missing_package = tmp_path / "missing-package"
    twin = DigitalTwinService(
        db_path=tmp_path / "support.db",
        cco_package_dir=missing_package,
        snomed_package_dir=missing_package,
        eager_load=True,
    )
    retriever = ScriptedRetriever(
        [
            ScoredChunk(
                id="bagisiklik-0",
                text="Eğitim sözlüğü. Hastalık tanısı değildir.",
                source="bagisiklik.md",
                score=4.0,
            )
        ]
    )
    try:
        assert twin._repo is not None
        twin._repo.ingest_bundle(bundle)
        prepared = twin.prepare_turn(
            "Hipotiroidi tanısı daha önce olmuş mu?",
            case_id="oracle-pilot-018",
            retriever=retriever,
        )
        ids = [item.citation_id for item in prepared.evidence.patient_cco]
        assert prepared.plan.intent == "clinical_history_search"
        assert "CCO:oracle-pilot-018:F442" in ids
        assert "CCO:oracle-pilot-018:F500" in ids
        assert "CCO:oracle-pilot-018:F499" not in ids
        assert "CCO:oracle-pilot-018:F1105" not in ids
        assert prepared.evidence.general_knowledge == []
        assert "GENEL:bagisiklik-0" not in prepared.evidence.allowed_citation_ids
        assert "ön tanı" in prepared.history_answer
        assert "2026-04-08" in prepared.history_answer
        assert "F442" in prepared.history_answer
        assert "kesin tanı" not in prepared.history_answer
        assert "F499" not in prepared.history_answer
        assert "F1105" not in prepared.history_answer
    finally:
        twin.close()


def test_history_builder_drops_dictionary_chunks() -> None:
    bundle = EvidenceBuilder().build(
        case_id="oracle-pilot-018",
        snapshot=None,
        general_chunks=[
            ScoredChunk(
                id="bagisiklik-0",
                text="Hastalık tanısı değildir.",
                source="bagisiklik.md",
                score=3.0,
            )
        ],
        history_mode=True,
        history_facts=[],
        history_prefixes=("E0",),
        history_status="MATCH",
        history_concepts=(("40930008", "Hypothyroidism"),),
    )
    assert bundle.general_knowledge == []


def test_deterministic_history_answer_does_not_call_the_model(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from medical_rag.main import create_app

    bundle = AdaptedPatientBundle(
        case_id="oracle-pilot-018",
        subject_fingerprint="synthetic",
        evaluated_at="2026-11-01T00:00:00+03:00",
        exported_at="2026-11-01T00:00:00+03:00",
        cco_as_of="2026-11-01T00:00:00+03:00",
        export_scope="test",
        has_structured_data=True,
        total_rows=1,
        value_fact_count=1,
        missing_result_count=0,
        families=["diagnosis"],
        facts=[_fact(fact_alias="F442", source_index=442)],
        glossary=[],
        narrative_sections=[],
    )
    missing_package = tmp_path / "missing-package"
    twin = DigitalTwinService(
        db_path=tmp_path / "history-api.db",
        cco_package_dir=missing_package,
        snomed_package_dir=missing_package,
        eager_load=True,
    )
    fake = FakeOllama(text="model yazmamalı", prompt_eval_count=12)
    retriever = ScriptedRetriever(
        [
            ScoredChunk(
                id="bagisiklik-0",
                text="Hastalık tanısı değildir.",
                source="bagisiklik.md",
                score=4.0,
            )
        ]
    )
    try:
        assert twin._repo is not None
        twin._repo.ingest_bundle(bundle)
        app = create_app(ollama=fake, twin=twin, retriever=retriever)
        with TestClient(app) as client:
            response = client.post(
                "/v1/chat",
                json={
                    "question": "Geçmişimde tiroit hastalığı var mı?",
                    "case_id": "oracle-pilot-018",
                    "top_k": 3,
                },
            )
        body = response.json()
        assert response.status_code == 200
        assert fake.calls == 0
        assert body["intent"] == "clinical_history_search"
        assert body["eval_count"] == 0
        assert body["prompt_eval_count"] == 0
        assert body["abstained"] is False
        assert "F442" in body["answer"]
        assert "ön tanı" in body["answer"]
        assert "2026-04-08" in body["answer"]
        assert "GENEL:bagisiklik-0" not in body["retrieved_chunk_ids"]
        assert body["evidence_layers"]["general_knowledge"] == []
    finally:
        twin.close()
