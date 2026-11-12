import json
import re
from pathlib import Path

from medical_rag.config import Settings
from medical_rag.twin.cco_adapter import adapt_source_payload, load_patient_bundle
from medical_rag.twin.fact_repository import PatientFactRepository
from medical_rag.twin.temporal_resolver import TemporalResolver, is_derived_window_metric

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
)


def test_full_20_cases_match_reconstruction_and_hide_opaque_ids() -> None:
    settings = Settings()
    recon_path = settings.cco_package_dir / "source_reconstruction.json"
    expected_recon = {
        row["case_id"]: row["source_rows"]
        for row in json.loads(recon_path.read_text(encoding="utf-8"))
    }

    repo = PatientFactRepository(Path(":memory:"))
    total_ingested = repo.ensure_ingested(settings.cco_package_dir)
    assert total_ingested == 13788
    assert repo.patient_count() == 20

    patients = repo.list_patients()
    assert len(patients) == 20
    assert sum(p.value_fact_count for p in patients) == 8617
    assert sum(p.missing_result_count for p in patients) == 5171

    for patient in patients:
        assert patient.total_rows == expected_recon[patient.case_id]

    p19 = repo.get_patient("oracle-pilot-019")
    p20 = repo.get_patient("oracle-pilot-020")
    assert p19 is not None and p19.has_structured_data is False and p19.total_rows == 0
    assert p20 is not None and p20.has_structured_data is False and p20.total_rows == 0

    # Self-reported sections from original_cco.text must be captured across cohort
    all_self_reported = [
        sec.heading
        for p in patients
        for sec in repo.get_narrative_sections(p.case_id, self_reported_only=True)
    ]
    assert "Kullandığı ilaçlar (hasta beyanı)" in all_self_reported
    assert "Alerjiler (hasta beyanı)" in all_self_reported

    # Verify zero UUID leakage across SQLite columns
    raw_s01 = json.loads(
        (settings.cco_package_dir / "source_oracle-pilot-001.json").read_text(encoding="utf-8")
    )
    raw_subject_id = raw_s01["local_projection"]["subject_id"]
    for table in ("patients", "patient_facts", "fact_evidence", "patient_narrative_sections"):
        rows = repo.connection.execute(f"SELECT * FROM {table} LIMIT 300").fetchall()
        for row in rows:
            joined = " ".join(str(v) for v in dict(row).values() if v is not None)
            assert raw_subject_id not in joined
            assert not _UUID_RE.search(joined), f"{table} içinde opak UUID sızıntısı"

    repo.close()


def test_event_time_recorded_time_and_missing_data_are_distinct() -> None:
    settings = Settings()
    bundle = load_patient_bundle(settings.cco_package_dir / "source_oracle-pilot-001.json")
    repo = PatientFactRepository(Path(":memory:"))
    repo.ingest_bundle(bundle)
    resolver = TemporalResolver(repo)

    sleep_facts = repo.query_facts(
        "oracle-pilot-001",
        canonical_ids=["sleep.duration.last-main-sleep"],
    )
    assert len(sleep_facts) >= 1
    latest_sleep = sleep_facts[0]
    assert latest_sleep.unit == "minute"
    assert latest_sleep.amount is not None and latest_sleep.amount > 0
    assert latest_sleep.occurred_from < latest_sleep.occurred_to
    assert latest_sleep.recorded_at != latest_sleep.occurred_from
    assert len(latest_sleep.evidence) >= 1
    assert latest_sleep.evidence[0].occurred_at

    # Missing HRV personal baseline must be grouped as data-required, never zero
    hrv_missing = repo.summarize_missing_data(
        "oracle-pilot-001",
        canonical_prefix="cardio.hrv.personal-baseline",
    )
    assert len(hrv_missing) >= 1
    assert any(
        any(reason.startswith("minimumSamples:") for reason in grp.missing_reasons)
        for grp in hrv_missing
    )

    # Derived 7d-average must NOT be re-averaged as a daily series in snapshot
    assert is_derived_window_metric("sleep.duration.7d-average") is True
    assert is_derived_window_metric("sleep.duration.last-main-sleep") is False
    snapshot = resolver.build_snapshot(
        "oracle-pilot-001",
        "Son 7 günde uykum ve kalp verilerim nasıl?",
        families=["sleep", "cardio"],
    )
    assert snapshot is not None
    assert snapshot.window.days == 7
    assert all(
        not is_derived_window_metric(s.canonical_id)
        for s in snapshot.numeric_summaries
    )
    repo.close()


def test_supersession_chain_excludes_predecessor_and_superseded_rows() -> None:
    synthetic_payload = {
        "original_cco": {
            "id": "cco-doc-1",
            "subjectId": "11111111-2222-3333-4444-555555555555",
            "asOf": "2026-10-21T12:00:00+03:00",
            "text": "## Kullandığı ilaçlar (hasta beyanı)\n- Magnezyum takviyesi",
        },
        "local_projection": {
            "format": "cco-local-projection/1",
            "subject_id": "11111111-2222-3333-4444-555555555555",
            "evaluated_at": "2026-10-21T12:00:00+03:00",
            "exported_at": "2026-10-21T12:05:00+03:00",
            "export_metadata": {"scope": "test-with-history"},
            "glossary": {
                "facts": {
                    "vitals.weight.latest|1.0.0": {
                        "label": "Son kilo",
                        "description": "Kayıtlı en güncel vücut ağırlığı.",
                    }
                },
                "families": {},
                "rules": {},
            },
            "sections": {
                "vitals": {
                    "facts": [
                        {
                            "factId": "aaaa0001-0000-0000-0000-000000000001",
                            "definition": "vitals.weight.latest|1.0.0",
                            "evaluationKey": "latest",
                            "evaluationStatus": "success",
                            "value": {"type": "quantity", "amount": 80.0, "unit": "kg"},
                            "occurredFrom": "2026-10-18T09:00:00+03:00",
                            "occurredTo": "2026-10-18T09:00:00+03:00",
                            "recordedAt": "2026-10-18T09:05:00+03:00",
                            "validUntil": None,
                            "comparisons": [],
                            "evidence": [
                                {
                                    "sourceId": "ev-001",
                                    "sourceType": "measurement.body-weight",
                                    "role": "source",
                                    "occurredAt": "2026-10-18T09:00:00+03:00",
                                }
                            ],
                            "source_issues": [],
                            "provenance": {
                                "source_index": 0,
                                "source_row_sha256": "h1",
                                "nested_value": True,
                                "legacy_value_fields": {},
                                "auxiliary_fields": {"constraints": {}, "missingData": []},
                                "export_fields": {
                                    "engineVersion": "evaluator/1.0.0",
                                    "nextEvaluationAt": None,
                                    "status": "active",
                                    "supersedeReason": None,
                                    "supersededAt": None,
                                    "supersedesFactId": None,
                                    "validFrom": "2026-10-18T09:05:00+03:00",
                                },
                            },
                        },
                        {
                            "factId": "aaaa0002-0000-0000-0000-000000000002",
                            "definition": "vitals.weight.latest|1.0.0",
                            "evaluationKey": "latest",
                            "evaluationStatus": "success",
                            "value": {"type": "quantity", "amount": 78.5, "unit": "kg"},
                            "occurredFrom": "2026-10-20T09:00:00+03:00",
                            "occurredTo": "2026-10-20T09:00:00+03:00",
                            "recordedAt": "2026-10-20T09:05:00+03:00",
                            "validUntil": None,
                            "comparisons": [],
                            "evidence": [
                                {
                                    "sourceId": "ev-002",
                                    "sourceType": "measurement.body-weight",
                                    "role": "source",
                                    "occurredAt": "2026-10-20T09:00:00+03:00",
                                }
                            ],
                            "source_issues": [],
                            "provenance": {
                                "source_index": 1,
                                "source_row_sha256": "h2",
                                "nested_value": True,
                                "legacy_value_fields": {},
                                "auxiliary_fields": {"constraints": {}, "missingData": []},
                                "export_fields": {
                                    "engineVersion": "evaluator/1.0.0",
                                    "nextEvaluationAt": None,
                                    "status": "active",
                                    "supersedeReason": "data-correction",
                                    "supersededAt": None,
                                    "supersedesFactId": "aaaa0001-0000-0000-0000-000000000001",
                                    "validFrom": "2026-10-20T09:05:00+03:00",
                                },
                            },
                        },
                        {
                            "factId": "aaaa0003-0000-0000-0000-000000000003",
                            "definition": "vitals.weight.latest|1.0.0",
                            "evaluationKey": "latest",
                            "evaluationStatus": "success",
                            "value": {"type": "quantity", "amount": 99.0, "unit": "kg"},
                            "occurredFrom": "2026-10-19T09:00:00+03:00",
                            "occurredTo": "2026-10-19T09:00:00+03:00",
                            "recordedAt": "2026-10-19T09:05:00+03:00",
                            "validUntil": None,
                            "comparisons": [],
                            "evidence": [],
                            "source_issues": [],
                            "provenance": {
                                "source_index": 2,
                                "source_row_sha256": "h3",
                                "nested_value": True,
                                "legacy_value_fields": {},
                                "auxiliary_fields": {"constraints": {}, "missingData": []},
                                "export_fields": {
                                    "engineVersion": "evaluator/1.0.0",
                                    "nextEvaluationAt": None,
                                    "status": "superseded",
                                    "supersedeReason": None,
                                    "supersededAt": "2026-10-20T09:05:00+03:00",
                                    "supersedesFactId": None,
                                    "validFrom": "2026-10-19T09:05:00+03:00",
                                },
                            },
                        },
                    ],
                    "missingData": [],
                }
            },
        },
    }

    bundle = adapt_source_payload("oracle-pilot-099", synthetic_payload)
    assert bundle.facts[1].supersedes_fact_alias == "F1"

    repo = PatientFactRepository(Path(":memory:"))
    repo.ingest_bundle(bundle)

    active_facts = repo.query_facts("oracle-pilot-099", active_only=True)
    assert [f.fact_alias for f in active_facts] == ["F2"]
    assert active_facts[0].amount == 78.5

    stats = repo.compute_numeric_stats("oracle-pilot-099", "vitals.weight.latest")
    assert stats is not None
    assert stats.sample_count == 1
    assert stats.latest_amount == 78.5
    assert stats.avg_amount == 78.5
    repo.close()
