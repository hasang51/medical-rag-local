"""G5 Digital Twin orkestrasyon servisi.

Veritabanı yaşam döngüsünü (`PatientFactRepository` + `SnomedImporter`),
niyet yönlendirmeyi (`IntentRouter`), zaman çözümlemeyi (`TemporalResolver`) ve
üç katmanlı kanıt üretimini (`EvidenceBuilder`) tek bir güvenli arayüzde birleştirir.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from medical_rag.rag.retriever import Retriever, ScoredChunk
from medical_rag.terminology.concept_linker import ConceptLinker
from medical_rag.terminology.snomed_importer import SnomedImporter
from medical_rag.twin.clinical_history import (
    HistoryQuery,
    classify_history_search,
    compose_coded_history_answer,
)
from medical_rag.twin.evidence_builder import EvidenceBuilder, LayeredEvidenceBundle
from medical_rag.twin.fact_repository import PatientFactRepository, PatientSummary
from medical_rag.twin.intent_router import IntentRouter, RoutePlan
from medical_rag.twin.temporal_resolver import (
    PatientTemporalSnapshot,
    ResolvedFactView,
    TemporalResolver,
    is_derived_window_metric,
    parse_iso_timestamp,
)


@dataclass(frozen=True)
class PreparedTwinTurn:
    plan: RoutePlan
    patient: PatientSummary | None
    snapshot: PatientTemporalSnapshot | None
    evidence: LayeredEvidenceBundle
    rendered_context: str
    history_answer: str = ""


class DigitalTwinService:
    """Kişisel CCO kayıtları + SNOMED CT IPS + Genel BM25 kanıtlarını hazırlar."""

    def __init__(
        self,
        *,
        db_path: Path,
        cco_package_dir: Path,
        snomed_package_dir: Path,
        eager_load: bool = False,
    ) -> None:
        self._db_path = db_path
        self._cco_package_dir = cco_package_dir
        self._snomed_package_dir = snomed_package_dir
        self._repo: PatientFactRepository | None = None
        self._snomed: SnomedImporter | None = None
        self._linker: ConceptLinker | None = None
        self._resolver: TemporalResolver | None = None
        self._router: IntentRouter | None = None
        self._evidence_builder = EvidenceBuilder()
        if eager_load:
            self._ensure_ready()

    def _ensure_ready(self) -> None:
        if self._repo is None:
            self._repo = PatientFactRepository(self._db_path)
            self._repo.ensure_ingested(self._cco_package_dir)
            self._snomed = SnomedImporter(self._repo.connection)
            self._snomed.ensure_imported(self._snomed_package_dir)
            self._linker = ConceptLinker(self._repo.connection)
            self._resolver = TemporalResolver(self._repo)
            self._router = IntentRouter(self._linker)

    def close(self) -> None:
        if self._repo is not None:
            self._repo.close()
            self._repo = None

    def list_patients(self) -> list[PatientSummary]:
        self._ensure_ready()
        assert self._repo is not None
        return self._repo.list_patients()

    def get_patient(self, case_id: str) -> PatientSummary | None:
        self._ensure_ready()
        assert self._repo is not None
        return self._repo.get_patient(case_id)

    def prepare_turn(
        self,
        question: str,
        *,
        case_id: str,
        retriever: Retriever,
        top_k: int = 3,
    ) -> PreparedTwinTurn:
        self._ensure_ready()
        assert self._repo is not None
        assert self._resolver is not None
        assert self._router is not None

        general_hits: list[ScoredChunk] = retriever.retrieve(question, top_k)
        plan = self._router.route(
            question,
            case_id=case_id,
            has_corpus_hits=len(general_hits) > 0,
        )
        patient = self._repo.get_patient(case_id)

        if plan.intent == "clinical_history_search" and patient is not None:
            coded = []
            related = []
            if patient.has_structured_data and plan.history_prefixes:
                coded = self._repo.query_coded_history(case_id, plan.history_prefixes)
                days = {
                    (fact.occurred_from or "")[:10]
                    for fact in coded
                    if fact.occurred_from
                }
                days.update(
                    (fact.occurred_to or "")[:10] for fact in coded if fact.occurred_to
                )
                related = self._repo.query_same_day_context(case_id, days)
            glossary = self._repo.get_glossary_map(case_id)
            ref_dt = parse_iso_timestamp(patient.evaluated_at or patient.cco_as_of)
            history_views: list[ResolvedFactView] = []
            for fact in [*coded, *related]:
                entry = glossary.get(fact.definition) or glossary.get(fact.canonical_id)
                valid_until = parse_iso_timestamp(fact.valid_until) if fact.valid_until else None
                history_views.append(
                    ResolvedFactView(
                        fact=fact,
                        glossary_label=entry.label if entry else fact.canonical_id,
                        glossary_description=entry.description if entry else "",
                        is_point_event=(fact.occurred_from == fact.occurred_to),
                        is_derived_window=is_derived_window_metric(fact.canonical_id),
                        is_expired_at_reference=bool(
                            ref_dt is not None and valid_until is not None and valid_until < ref_dt
                        ),
                    )
                )
            history_status = classify_history_search(
                HistoryQuery(active=True, code_prefixes=plan.history_prefixes),
                len(coded),
            )
            evidence = self._evidence_builder.build(
                case_id=case_id,
                snapshot=None,
                linked_concepts=plan.linked_concepts,
                general_chunks=general_hits,
                history_mode=True,
                history_facts=history_views,
                history_prefixes=plan.history_prefixes,
                history_status=history_status,
                history_concepts=plan.history_concepts,
            )
            # #region agent log
            try:
                import json as _json
                import time as _time

                with open(
                    r"c:\Projects\medical-rag-local\.cursor\debug-36fe44.log",
                    "a",
                    encoding="utf-8",
                ) as _fh:
                    _fh.write(
                        _json.dumps(
                            {
                                "sessionId": "36fe44",
                                "hypothesisId": "C",
                                "location": "service.py:prepare_turn",
                                "message": "history evidence composition",
                                "data": {
                                    "caseId": case_id,
                                    "question": question,
                                    "prefixes": list(plan.history_prefixes),
                                    "codedCount": len(coded),
                                    "relatedCount": len(related),
                                    "historyViewCount": len(history_views),
                                    "ccoCitationCount": len(evidence.patient_cco),
                                    "ccoCitations": [item.citation_id for item in evidence.patient_cco],
                                    "families": [
                                        fact.family for fact in [*coded, *related]
                                    ],
                                },
                                "timestamp": int(_time.time() * 1000),
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
            except Exception:
                pass
            # #endregion
            rendered_context = evidence.render_prompt_context(max_chars=7500)
            # #region agent log
            try:
                import json as _json
                import time as _time

                marker = "F442"
                idx = rendered_context.find(marker)
                excerpt = rendered_context[max(0, idx - 80) : idx + 700] if idx >= 0 else ""
                with open(
                    r"c:\Projects\medical-rag-local\.cursor\debug-36fe44.log",
                    "a",
                    encoding="utf-8",
                ) as _fh:
                    _fh.write(
                        _json.dumps(
                            {
                                "sessionId": "36fe44",
                                "hypothesisId": "P",
                                "location": "service.py:history_prompt",
                                "message": "history prompt fact presence",
                                "data": {
                                    "caseId": case_id,
                                    "promptChars": len(rendered_context),
                                    "factInPrompt": marker in rendered_context,
                                    "codeInPrompt": "E03" in rendered_context,
                                    "preliminaryInPrompt": "preliminary" in rendered_context,
                                    "visitDateInPrompt": "visitDate" in rendered_context,
                                    "excerpt": excerpt,
                                },
                                "timestamp": int(_time.time() * 1000),
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
            except Exception:
                pass
            # #endregion
            return PreparedTwinTurn(
                plan=plan,
                patient=patient,
                snapshot=None,
                evidence=evidence,
                rendered_context=rendered_context,
                history_answer=compose_coded_history_answer(
                    case_id=case_id,
                    status=history_status,
                    coded_facts=coded,
                ),
            )

        if plan.intent in {"emergency", "out_of_scope"} or patient is None:
            empty_bundle = self._evidence_builder.build(
                case_id=case_id,
                snapshot=None,
                linked_concepts=plan.linked_concepts,
                general_chunks=general_hits,
            )
            return PreparedTwinTurn(
                plan=plan,
                patient=patient,
                snapshot=None,
                evidence=empty_bundle,
                rendered_context="",
            )

        snapshot = self._resolver.build_snapshot(
            case_id,
            question,
            families=plan.target_families or None,
            priority_canonical_ids=plan.target_canonical_ids or None,
        )

        # Doğrudan canonical_id ipucu eşleştiyse en güncel aktif satırlarını da garantiye al
        targeted_views: list[ResolvedFactView] = []
        if plan.target_canonical_ids and patient.has_structured_data:
            glossary = self._repo.get_glossary_map(case_id)
            ref_dt = parse_iso_timestamp(patient.evaluated_at or patient.cco_as_of)
            for cid in plan.target_canonical_ids:
                rows = self._repo.query_facts(
                    case_id,
                    canonical_ids=[cid],
                    evaluation_status="success",
                    active_only=True,
                    limit=2,
                )
                for fact in rows:
                    g_entry = glossary.get(fact.definition) or glossary.get(fact.canonical_id)
                    v_dt = parse_iso_timestamp(fact.valid_until) if fact.valid_until else None
                    targeted_views.append(
                        ResolvedFactView(
                            fact=fact,
                            glossary_label=g_entry.label if g_entry else fact.canonical_id,
                            glossary_description=g_entry.description if g_entry else "",
                            is_point_event=(fact.occurred_from == fact.occurred_to),
                            is_derived_window=is_derived_window_metric(fact.canonical_id),
                            is_expired_at_reference=bool(
                                ref_dt is not None and v_dt is not None and v_dt < ref_dt
                            ),
                        )
                    )

        evidence = self._evidence_builder.build(
            case_id=case_id,
            snapshot=snapshot,
            targeted_facts=targeted_views,
            linked_concepts=plan.linked_concepts,
            general_chunks=general_hits,
        )
        rendered_context = evidence.render_prompt_context(max_chars=7500)
        return PreparedTwinTurn(
            plan=plan,
            patient=patient,
            snapshot=snapshot,
            evidence=evidence,
            rendered_context=rendered_context,
        )
