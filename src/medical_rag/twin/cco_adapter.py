"""CCO kaynak paketini salt-okunur okuyan ve opak kimliklerden arındıran adaptör.

Gerçek `source_oracle-pilot-NNN.json` dosyalarındaki `local_projection` (`facts`,
`missingData`, `glossary`, `provenance`, `evidence`, `comparisons`, `source_issues`)
ve `original_cco.text` içindeki hasta beyanı bölümlerini normalize eder.

Opak kimlikler (`subjectId`, `factId`, `sourceId`, `supersedesFactId`, `facilityId`,
`externalVisitId`, `latestExternalPrescriptionId`) yerel SQLite veya API katmanına
taşınmaz; vaka içi deterministik takma adlara (`F1..Fn`, `E1..Em`, `P1..Pk`) çevrilir.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_CASE_ID_RE = re.compile(r"^oracle-pilot-\d{3}$")
_UUID_OR_HEX_RE = re.compile(
    r"(?:[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}|[0-9a-fA-F]{24,64})"
)

# Klinik olarak anlamlı olan, opak tesis/ziyaret kimliği taşımayan öznitelikler
_SAFE_CLINICAL_ATTRS = frozenset(
    {
        "departmentName",
        "type",
        "visitDate",
        "latestPrescriptionDate",
        "examName",
        "performedAt",
        "approvedAt",
        "requestedAt",
        "requestingDepartment",
    }
)

# original_cco.text içindeki başlıkların CCO aile eşlemesi ve hasta beyanı bayrağı
_HEADING_METADATA: dict[str, tuple[str, str, bool]] = {
    "Kullandığı ilaçlar (hasta beyanı)": ("medications_self", "medication", True),
    "Hastalıklar (hasta beyanı)": ("conditions_self", "diagnosis", True),
    "Aile öyküsü (hasta beyanı)": ("family_history_self", "diagnosis", True),
    "Alerjiler (hasta beyanı)": ("allergies_self", "allergy", True),
    "Ameliyat ve işlemler": ("procedures_note", "visit", True),
    "Bilinmeyenler": ("unknowns_note", "data", False),
    "Tansiyon (evde ölçülen)": ("home_bp_note", "vitals", False),
    "Kan şekeri (evde ölçülen)": ("home_glucose_note", "glucose", False),
    "Tanılar (hastane kaydı)": ("diagnoses_emr", "diagnosis", False),
    "İlaçlar (reçete kaydı)": ("prescriptions_emr", "medication", False),
    "Hastane başvuruları": ("visits_emr", "visit", False),
    "Görüntüleme": ("imaging_emr", "imaging", False),
    "Laboratuvar (hastane)": ("lab_emr", "lab", False),
    "Patoloji": ("pathology_emr", "pathology", False),
    "Vücut ölçüleri": ("vitals_note", "vitals", False),
    "Uyku (yüzük)": ("sleep_note", "sleep", False),
    "Kalp (yüzük ve saat)": ("cardio_note", "cardio", False),
    "Solunum, oksijen ve sıcaklık (yüzük)": ("recovery_oxygen_note", "recovery", False),
    "Hareket": ("activity_note", "activity", False),
    "Stres": ("stress_note", "wellness", False),
    "Veri durumu": ("data_status_note", "data", False),
}


@dataclass(frozen=True)
class AdaptedEvidence:
    evidence_alias: str
    source_type: str
    role: str
    occurred_at: str


@dataclass(frozen=True)
class AdaptedComparison:
    kind: str
    target: float | None
    delta: float | None
    unit: str | None
    target_source: str | None


@dataclass(frozen=True)
class AdaptedGlossaryEntry:
    definition: str
    canonical_id: str
    version: str
    family: str
    label: str
    description: str


@dataclass(frozen=True)
class AdaptedNarrativeSection:
    section_slug: str
    heading: str
    family_hint: str
    is_self_reported: bool
    content: str


@dataclass(frozen=True)
class AdaptedFact:
    case_id: str
    fact_alias: str
    source_index: int
    family: str
    collection_kind: str
    definition: str
    canonical_id: str
    definition_version: str
    evaluation_key: str
    evaluation_status: str
    value_type: str | None
    amount: float | None
    unit: str | None
    code_system: str | None
    code: str | None
    display_text: str | None
    narrative_sections: dict[str, str]
    clinical_attributes: dict[str, str]
    truncated: bool
    occurred_from: str
    occurred_to: str
    recorded_at: str
    valid_from: str
    valid_until: str | None
    export_status: str
    superseded_at: str | None
    supersedes_fact_alias: str | None
    supersede_reason: str | None
    engine_version: str
    missing_reasons: list[str] = field(default_factory=list)
    source_issues: list[str] = field(default_factory=list)
    evidence: list[AdaptedEvidence] = field(default_factory=list)
    comparisons: list[AdaptedComparison] = field(default_factory=list)


@dataclass(frozen=True)
class AdaptedPatientBundle:
    case_id: str
    subject_fingerprint: str
    evaluated_at: str
    exported_at: str
    cco_as_of: str
    export_scope: str
    has_structured_data: bool
    total_rows: int
    value_fact_count: int
    missing_result_count: int
    families: list[str]
    facts: list[AdaptedFact]
    glossary: list[AdaptedGlossaryEntry]
    narrative_sections: list[AdaptedNarrativeSection]


def _split_definition(definition: str) -> tuple[str, str]:
    if "|" in definition:
        canonical_id, version = definition.split("|", 1)
        return canonical_id, version
    return definition, ""


def _to_float(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _sanitize_text_identifiers(text: str, sample_aliases: dict[str, str]) -> str:
    def _replace(match: re.Match[str]) -> str:
        raw = match.group(0)
        if raw not in sample_aliases:
            sample_aliases[raw] = f"S{len(sample_aliases) + 1}"
        return sample_aliases[raw]

    return _UUID_OR_HEX_RE.sub(_replace, text)


def parse_original_cco_sections(
    text: str,
    sample_aliases: dict[str, str] | None = None,
) -> list[AdaptedNarrativeSection]:
    """`original_cco.text` içindeki `## ...` bölümlerini ayrıştırır."""
    aliases = sample_aliases if sample_aliases is not None else {}
    sections: list[AdaptedNarrativeSection] = []
    current_heading: str | None = None
    buffer: list[str] = []

    def _flush() -> None:
        if current_heading is None:
            return
        body = "\n".join(line.rstrip() for line in buffer).strip()
        if not body:
            return
        sanitized_body = _sanitize_text_identifiers(body, aliases)
        slug, family_hint, is_self_reported = _HEADING_METADATA.get(
            current_heading,
            (
                re.sub(r"[^a-z0-9]+", "_", current_heading.lower()).strip("_") or "section",
                "general",
                "hasta beyanı" in current_heading.lower(),
            ),
        )
        sections.append(
            AdaptedNarrativeSection(
                section_slug=slug,
                heading=current_heading,
                family_hint=family_hint,
                is_self_reported=is_self_reported,
                content=sanitized_body,
            )
        )

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            _flush()
            current_heading = stripped.removeprefix("## ").strip()
            buffer = []
        elif current_heading is not None:
            buffer.append(line)
    _flush()
    return sections


def adapt_source_payload(case_id: str, payload: dict[str, Any]) -> AdaptedPatientBundle:
    """Tek bir `source_oracle-pilot-NNN.json` nesnesini güvenli G5 veri modeline dönüştürür."""
    if not _CASE_ID_RE.fullmatch(case_id):
        raise ValueError(f"Geçersiz vaka kimliği: {case_id}")

    projection = payload.get("local_projection") or {}
    original_cco = payload.get("original_cco") or {}
    if projection.get("format") != "cco-local-projection/1":
        raise ValueError(f"Desteklenmeyen CCO projeksiyon formatı: {projection.get('format')}")

    raw_subject_id = str(projection.get("subject_id") or original_cco.get("subjectId") or "")
    if not raw_subject_id:
        raise ValueError(f"{case_id} içinde subject_id eksik")
    if original_cco.get("subjectId") and str(original_cco["subjectId"]) != raw_subject_id:
        raise ValueError(f"{case_id} içinde subject_id uyuşmazlığı")

    subject_fingerprint = hashlib.sha256(raw_subject_id.encode("utf-8")).hexdigest()[:12]

    # 1. Geçiş: tüm factId -> F{source_index + 1} eşlemesi
    raw_rows: list[tuple[str, str, dict[str, Any]]] = []
    fact_id_to_alias: dict[str, str] = {}
    for family, section in sorted((projection.get("sections") or {}).items()):
        for collection_kind in ("facts", "missingData"):
            for row in section.get(collection_kind) or []:
                source_index = int(row["provenance"]["source_index"])
                alias = f"F{source_index + 1}"
                raw_fact_id = str(row["factId"])
                if raw_fact_id in fact_id_to_alias and fact_id_to_alias[raw_fact_id] != alias:
                    raise ValueError(f"{case_id} içinde yinelenen factId takma adı")
                fact_id_to_alias[raw_fact_id] = alias
                raw_rows.append((family, collection_kind, row))

    raw_rows.sort(key=lambda item: int(item[2]["provenance"]["source_index"]))

    predecessor_aliases: dict[str, str] = {}
    evidence_aliases: dict[str, str] = {}
    sample_aliases: dict[str, str] = {}

    def _resolve_predecessor(raw_pred_id: Any) -> str | None:
        if not raw_pred_id:
            return None
        pred_str = str(raw_pred_id)
        if pred_str in fact_id_to_alias:
            return fact_id_to_alias[pred_str]
        if pred_str not in predecessor_aliases:
            predecessor_aliases[pred_str] = f"P{len(predecessor_aliases) + 1}"
        return predecessor_aliases[pred_str]

    def _resolve_evidence_source(raw_source_id: Any) -> str:
        src_str = str(raw_source_id or "")
        if src_str in fact_id_to_alias:
            return fact_id_to_alias[src_str]
        if src_str not in evidence_aliases:
            evidence_aliases[src_str] = f"E{len(evidence_aliases) + 1}"
        return evidence_aliases[src_str]

    adapted_facts: list[AdaptedFact] = []
    for family, collection_kind, row in raw_rows:
        provenance = row["provenance"]
        source_index = int(provenance["source_index"])
        fact_alias = fact_id_to_alias[str(row["factId"])]
        definition = str(row["definition"])
        canonical_id, def_version = _split_definition(definition)
        eval_key = _sanitize_text_identifiers(str(row["evaluationKey"]), sample_aliases)
        eval_status = str(row["evaluationStatus"])

        val = row.get("value")
        value_type: str | None = None
        amount: float | None = None
        unit: str | None = None
        code_system: str | None = None
        code: str | None = None
        display_text: str | None = None
        narrative_sections: dict[str, str] = {}
        clinical_attributes: dict[str, str] = {}
        truncated = False

        if isinstance(val, dict):
            value_type = str(val.get("type") or "") or None
            unit = str(val.get("unit")) if val.get("unit") is not None else None
            amount = _to_float(val.get("amount"))
            if "system" in val and val["system"] is not None:
                code_system = str(val["system"])
            if "code" in val and val["code"] is not None:
                code = _sanitize_text_identifiers(str(val["code"]), sample_aliases)
            if "display" in val and val["display"] is not None:
                display_text = _sanitize_text_identifiers(str(val["display"]), sample_aliases)
            truncated = bool(val.get("truncated", False))
            raw_attrs = val.get("attributes")
            if isinstance(raw_attrs, dict):
                for attr_k, attr_v in raw_attrs.items():
                    if attr_k in _SAFE_CLINICAL_ATTRS and attr_v is not None:
                        clinical_attributes[attr_k] = _sanitize_text_identifiers(
                            str(attr_v), sample_aliases
                        )
            raw_sections = val.get("sections")
            if isinstance(raw_sections, dict):
                for sec_k, sec_v in raw_sections.items():
                    if sec_v is not None and str(sec_v).strip():
                        narrative_sections[str(sec_k)] = _sanitize_text_identifiers(
                            str(sec_v).strip(), sample_aliases
                        )

        export_fields = provenance.get("export_fields") or {}
        aux_fields = provenance.get("auxiliary_fields") or {}
        raw_missing = aux_fields.get("missingData") or []
        missing_reasons = [
            _sanitize_text_identifiers(str(item), sample_aliases)
            for item in raw_missing
            if item is not None
        ]
        raw_issues = row.get("source_issues") or []
        source_issues = [str(issue) for issue in raw_issues if issue is not None]

        evidence_items = [
            AdaptedEvidence(
                evidence_alias=_resolve_evidence_source(ev.get("sourceId")),
                source_type=str(ev.get("sourceType") or ""),
                role=str(ev.get("role") or "source"),
                occurred_at=str(ev.get("occurredAt") or ""),
            )
            for ev in (row.get("evidence") or [])
        ]

        comparison_items = [
            AdaptedComparison(
                kind=str(comp.get("kind") or ""),
                target=_to_float(comp.get("target")),
                delta=_to_float(comp.get("delta")),
                unit=str(comp["unit"]) if comp.get("unit") is not None else None,
                target_source=(
                    str(comp["targetSource"])
                    if comp.get("targetSource") is not None
                    else None
                ),
            )
            for comp in (row.get("comparisons") or [])
            if isinstance(comp, dict)
        ]

        adapted_facts.append(
            AdaptedFact(
                case_id=case_id,
                fact_alias=fact_alias,
                source_index=source_index,
                family=family,
                collection_kind=collection_kind,
                definition=definition,
                canonical_id=canonical_id,
                definition_version=def_version,
                evaluation_key=eval_key,
                evaluation_status=eval_status,
                value_type=value_type,
                amount=amount,
                unit=unit,
                code_system=code_system,
                code=code,
                display_text=display_text,
                narrative_sections=narrative_sections,
                clinical_attributes=clinical_attributes,
                truncated=truncated,
                occurred_from=str(row.get("occurredFrom") or ""),
                occurred_to=str(row.get("occurredTo") or ""),
                recorded_at=str(row.get("recordedAt") or ""),
                valid_from=str(export_fields.get("validFrom") or ""),
                valid_until=(
                    str(row["validUntil"]) if row.get("validUntil") is not None else None
                ),
                export_status=str(export_fields.get("status") or "active"),
                superseded_at=(
                    str(export_fields["supersededAt"])
                    if export_fields.get("supersededAt") is not None
                    else None
                ),
                supersedes_fact_alias=_resolve_predecessor(
                    export_fields.get("supersedesFactId")
                ),
                supersede_reason=(
                    str(export_fields["supersedeReason"])
                    if export_fields.get("supersedeReason") is not None
                    else None
                ),
                engine_version=str(export_fields.get("engineVersion") or ""),
                missing_reasons=missing_reasons,
                source_issues=source_issues,
                evidence=evidence_items,
                comparisons=comparison_items,
            )
        )

    glossary_entries: list[AdaptedGlossaryEntry] = []
    glossary_facts = (projection.get("glossary") or {}).get("facts") or {}
    if isinstance(glossary_facts, dict):
        for definition, info in sorted(glossary_facts.items()):
            if not isinstance(info, dict):
                continue
            canonical_id, version = _split_definition(str(definition))
            family = canonical_id.split(".", 1)[0] if "." in canonical_id else "general"
            glossary_entries.append(
                AdaptedGlossaryEntry(
                    definition=str(definition),
                    canonical_id=canonical_id,
                    version=version,
                    family=family,
                    label=str(info.get("label") or canonical_id),
                    description=str(info.get("description") or ""),
                )
            )

    cco_text = str(original_cco.get("text") or "")
    narrative_sections = parse_original_cco_sections(cco_text, sample_aliases)

    value_count = sum(1 for item in adapted_facts if item.collection_kind == "facts")
    missing_count = sum(
        1 for item in adapted_facts if item.collection_kind == "missingData"
    )
    families = sorted({item.family for item in adapted_facts})
    export_meta = projection.get("export_metadata") or {}

    return AdaptedPatientBundle(
        case_id=case_id,
        subject_fingerprint=subject_fingerprint,
        evaluated_at=str(projection.get("evaluated_at") or ""),
        exported_at=str(projection.get("exported_at") or ""),
        cco_as_of=str(original_cco.get("asOf") or ""),
        export_scope=str(export_meta.get("scope") or ""),
        has_structured_data=len(adapted_facts) > 0,
        total_rows=len(adapted_facts),
        value_fact_count=value_count,
        missing_result_count=missing_count,
        families=families,
        facts=adapted_facts,
        glossary=glossary_entries,
        narrative_sections=narrative_sections,
    )


def load_patient_bundle(source_path: Path) -> AdaptedPatientBundle:
    """`source_oracle-pilot-NNN.json` dosyasını diskten salt-okunur okur."""
    stem = source_path.stem
    if not stem.startswith("source_"):
        raise ValueError(f"Beklenmeyen kaynak dosya adı: {source_path.name}")
    case_id = stem.removeprefix("source_")
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    return adapt_source_payload(case_id, payload)


def iter_patient_bundles(package_dir: Path) -> list[AdaptedPatientBundle]:
    """`package/` dizinindeki tüm `source_oracle-pilot-*.json` dosyalarını sırayla yükler."""
    paths = sorted(package_dir.glob("source_oracle-pilot-*.json"))
    return [load_patient_bundle(path) for path in paths]
