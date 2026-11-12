"""SQLite tabanlı hasta CCO kayıt deposu ve kesin SQL/Python hesaplama katmanı.

Sayı, tarih, son kayıt, min/max/ortalama ve eksik veri (`data-required`) gruplaması
LLM'e bırakılmaz; bu modülde SQL ve Python ile deterministik olarak hesaplanır.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from medical_rag.twin.cco_adapter import (
    AdaptedComparison,
    AdaptedEvidence,
    AdaptedFact,
    AdaptedGlossaryEntry,
    AdaptedNarrativeSection,
    AdaptedPatientBundle,
    iter_patient_bundles,
)


@dataclass(frozen=True)
class PatientSummary:
    case_id: str
    evaluated_at: str
    exported_at: str
    cco_as_of: str
    has_structured_data: bool
    total_rows: int
    value_fact_count: int
    missing_result_count: int
    families: list[str]
    self_reported_sections: list[str]


@dataclass(frozen=True)
class NumericSeriesSummary:
    case_id: str
    canonical_id: str
    unit: str | None
    sample_count: int
    min_amount: float
    max_amount: float
    avg_amount: float
    latest_amount: float
    latest_fact_alias: str
    latest_evaluation_key: str
    latest_occurred_from: str
    latest_occurred_to: str
    latest_recorded_at: str
    earliest_occurred_from: str


@dataclass(frozen=True)
class MissingDataGroupSummary:
    family: str
    canonical_id: str
    definition_version: str
    missing_reasons: list[str]
    row_count: int
    earliest_occurred_from: str
    latest_occurred_to: str
    sample_fact_aliases: list[str]


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS patients (
    case_id TEXT PRIMARY KEY,
    subject_fingerprint TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    exported_at TEXT NOT NULL,
    cco_as_of TEXT NOT NULL,
    export_scope TEXT NOT NULL,
    has_structured_data INTEGER NOT NULL,
    total_rows INTEGER NOT NULL,
    value_fact_count INTEGER NOT NULL,
    missing_result_count INTEGER NOT NULL,
    families_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cco_glossary (
    case_id TEXT NOT NULL,
    definition TEXT NOT NULL,
    canonical_id TEXT NOT NULL,
    version TEXT NOT NULL,
    family TEXT NOT NULL,
    label TEXT NOT NULL,
    description TEXT NOT NULL,
    PRIMARY KEY (case_id, definition)
);

CREATE TABLE IF NOT EXISTS patient_facts (
    case_id TEXT NOT NULL,
    fact_alias TEXT NOT NULL,
    source_index INTEGER NOT NULL,
    family TEXT NOT NULL,
    collection_kind TEXT NOT NULL,
    definition TEXT NOT NULL,
    canonical_id TEXT NOT NULL,
    definition_version TEXT NOT NULL,
    evaluation_key TEXT NOT NULL,
    evaluation_status TEXT NOT NULL,
    value_type TEXT,
    amount REAL,
    unit TEXT,
    code_system TEXT,
    code TEXT,
    display_text TEXT,
    narrative_sections_json TEXT NOT NULL,
    clinical_attributes_json TEXT NOT NULL,
    truncated INTEGER NOT NULL,
    occurred_from TEXT NOT NULL,
    occurred_to TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_until TEXT,
    export_status TEXT NOT NULL,
    superseded_at TEXT,
    supersedes_fact_alias TEXT,
    supersede_reason TEXT,
    engine_version TEXT NOT NULL,
    missing_reasons_json TEXT NOT NULL,
    source_issues_json TEXT NOT NULL,
    evidence_count INTEGER NOT NULL,
    PRIMARY KEY (case_id, fact_alias)
);

CREATE INDEX IF NOT EXISTS idx_facts_case_family_canon
    ON patient_facts (case_id, family, canonical_id, export_status);
CREATE INDEX IF NOT EXISTS idx_facts_case_status
    ON patient_facts (case_id, evaluation_status, occurred_to);
CREATE INDEX IF NOT EXISTS idx_facts_case_supersedes
    ON patient_facts (case_id, supersedes_fact_alias);

CREATE TABLE IF NOT EXISTS fact_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    fact_alias TEXT NOT NULL,
    evidence_alias TEXT NOT NULL,
    source_type TEXT NOT NULL,
    role TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_evidence_case_fact
    ON fact_evidence (case_id, fact_alias);

CREATE TABLE IF NOT EXISTS fact_comparisons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    fact_alias TEXT NOT NULL,
    kind TEXT NOT NULL,
    target REAL,
    delta REAL,
    unit TEXT,
    target_source TEXT
);

CREATE INDEX IF NOT EXISTS idx_comparisons_case_fact
    ON fact_comparisons (case_id, fact_alias);

CREATE TABLE IF NOT EXISTS patient_narrative_sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    section_slug TEXT NOT NULL,
    heading TEXT NOT NULL,
    family_hint TEXT NOT NULL,
    is_self_reported INTEGER NOT NULL,
    content TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_narrative_case_family
    ON patient_narrative_sections (case_id, family_hint, is_self_reported);
"""


class PatientFactRepository:
    """Yerel SQLite üzerinde CCO hasta verisini yönetir ve kesin sorgular çalıştırır."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        if str(db_path) != ":memory:":
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(_SCHEMA_SQL)

    def close(self) -> None:
        self._conn.close()

    def patient_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS cnt FROM patients").fetchone()
        return int(row["cnt"]) if row else 0

    def total_fact_rows(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS cnt FROM patient_facts").fetchone()
        return int(row["cnt"]) if row else 0

    def ensure_ingested(self, package_dir: Path) -> int:
        """Paket dizini mevcutsa ve veritabanı henüz yüklenmemişse idempotent olarak yükler."""
        if not package_dir.exists():
            return 0
        source_files = sorted(package_dir.glob("source_oracle-pilot-*.json"))
        if not source_files:
            return 0
        if self.patient_count() == len(source_files):
            return self.total_fact_rows()
        return self.ingest_directory(package_dir)

    def ingest_directory(self, package_dir: Path) -> int:
        bundles = iter_patient_bundles(package_dir)
        for bundle in bundles:
            self.ingest_bundle(bundle)
        return self.total_fact_rows()

    def ingest_bundle(self, bundle: AdaptedPatientBundle) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM fact_evidence WHERE case_id = ?", (bundle.case_id,))
            self._conn.execute("DELETE FROM fact_comparisons WHERE case_id = ?", (bundle.case_id,))
            self._conn.execute("DELETE FROM patient_facts WHERE case_id = ?", (bundle.case_id,))
            self._conn.execute("DELETE FROM cco_glossary WHERE case_id = ?", (bundle.case_id,))
            self._conn.execute(
                "DELETE FROM patient_narrative_sections WHERE case_id = ?",
                (bundle.case_id,),
            )
            self._conn.execute("DELETE FROM patients WHERE case_id = ?", (bundle.case_id,))

            self._conn.execute(
                """
                INSERT INTO patients (
                    case_id, subject_fingerprint, evaluated_at, exported_at, cco_as_of,
                    export_scope, has_structured_data, total_rows, value_fact_count,
                    missing_result_count, families_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bundle.case_id,
                    bundle.subject_fingerprint,
                    bundle.evaluated_at,
                    bundle.exported_at,
                    bundle.cco_as_of,
                    bundle.export_scope,
                    1 if bundle.has_structured_data else 0,
                    bundle.total_rows,
                    bundle.value_fact_count,
                    bundle.missing_result_count,
                    json.dumps(bundle.families, ensure_ascii=False),
                ),
            )

            if bundle.glossary:
                self._conn.executemany(
                    """
                    INSERT INTO cco_glossary (
                        case_id, definition, canonical_id, version, family, label, description
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            bundle.case_id,
                            entry.definition,
                            entry.canonical_id,
                            entry.version,
                            entry.family,
                            entry.label,
                            entry.description,
                        )
                        for entry in bundle.glossary
                    ],
                )

            if bundle.narrative_sections:
                self._conn.executemany(
                    """
                    INSERT INTO patient_narrative_sections (
                        case_id, section_slug, heading, family_hint, is_self_reported, content
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            bundle.case_id,
                            sec.section_slug,
                            sec.heading,
                            sec.family_hint,
                            1 if sec.is_self_reported else 0,
                            sec.content,
                        )
                        for sec in bundle.narrative_sections
                    ],
                )

            if bundle.facts:
                self._conn.executemany(
                    """
                    INSERT INTO patient_facts (
                        case_id, fact_alias, source_index, family, collection_kind,
                        definition, canonical_id, definition_version, evaluation_key,
                        evaluation_status, value_type, amount, unit, code_system, code,
                        display_text, narrative_sections_json, clinical_attributes_json,
                        truncated, occurred_from, occurred_to, recorded_at, valid_from,
                        valid_until, export_status, superseded_at, supersedes_fact_alias,
                        supersede_reason, engine_version, missing_reasons_json,
                        source_issues_json, evidence_count
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    [
                        (
                            fact.case_id,
                            fact.fact_alias,
                            fact.source_index,
                            fact.family,
                            fact.collection_kind,
                            fact.definition,
                            fact.canonical_id,
                            fact.definition_version,
                            fact.evaluation_key,
                            fact.evaluation_status,
                            fact.value_type,
                            fact.amount,
                            fact.unit,
                            fact.code_system,
                            fact.code,
                            fact.display_text,
                            json.dumps(fact.narrative_sections, ensure_ascii=False),
                            json.dumps(fact.clinical_attributes, ensure_ascii=False),
                            1 if fact.truncated else 0,
                            fact.occurred_from,
                            fact.occurred_to,
                            fact.recorded_at,
                            fact.valid_from,
                            fact.valid_until,
                            fact.export_status,
                            fact.superseded_at,
                            fact.supersedes_fact_alias,
                            fact.supersede_reason,
                            fact.engine_version,
                            json.dumps(fact.missing_reasons, ensure_ascii=False),
                            json.dumps(fact.source_issues, ensure_ascii=False),
                            len(fact.evidence),
                        )
                        for fact in bundle.facts
                    ],
                )

                ev_rows = [
                    (
                        fact.case_id,
                        fact.fact_alias,
                        ev.evidence_alias,
                        ev.source_type,
                        ev.role,
                        ev.occurred_at,
                    )
                    for fact in bundle.facts
                    for ev in fact.evidence
                ]
                if ev_rows:
                    self._conn.executemany(
                        """
                        INSERT INTO fact_evidence (
                            case_id, fact_alias, evidence_alias, source_type, role, occurred_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        ev_rows,
                    )

                comp_rows = [
                    (
                        fact.case_id,
                        fact.fact_alias,
                        comp.kind,
                        comp.target,
                        comp.delta,
                        comp.unit,
                        comp.target_source,
                    )
                    for fact in bundle.facts
                    for comp in fact.comparisons
                ]
                if comp_rows:
                    self._conn.executemany(
                        """
                        INSERT INTO fact_comparisons (
                            case_id, fact_alias, kind, target, delta, unit, target_source
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        comp_rows,
                    )

    def list_patients(self) -> list[PatientSummary]:
        rows = self._conn.execute(
            "SELECT * FROM patients ORDER BY case_id ASC"
        ).fetchall()
        return [self._row_to_patient_summary(row) for row in rows]

    def get_patient(self, case_id: str) -> PatientSummary | None:
        row = self._conn.execute(
            "SELECT * FROM patients WHERE case_id = ?", (case_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_patient_summary(row)

    def _row_to_patient_summary(self, row: sqlite3.Row) -> PatientSummary:
        case_id = str(row["case_id"])
        sr_rows = self._conn.execute(
            """
            SELECT heading FROM patient_narrative_sections
            WHERE case_id = ? AND is_self_reported = 1
            ORDER BY id ASC
            """,
            (case_id,),
        ).fetchall()
        return PatientSummary(
            case_id=case_id,
            evaluated_at=str(row["evaluated_at"]),
            exported_at=str(row["exported_at"]),
            cco_as_of=str(row["cco_as_of"]),
            has_structured_data=bool(row["has_structured_data"]),
            total_rows=int(row["total_rows"]),
            value_fact_count=int(row["value_fact_count"]),
            missing_result_count=int(row["missing_result_count"]),
            families=json.loads(str(row["families_json"])),
            self_reported_sections=[str(r["heading"]) for r in sr_rows],
        )

    def get_glossary_map(self, case_id: str) -> dict[str, AdaptedGlossaryEntry]:
        rows = self._conn.execute(
            "SELECT * FROM cco_glossary WHERE case_id = ?", (case_id,)
        ).fetchall()
        result: dict[str, AdaptedGlossaryEntry] = {}
        for row in rows:
            entry = AdaptedGlossaryEntry(
                definition=str(row["definition"]),
                canonical_id=str(row["canonical_id"]),
                version=str(row["version"]),
                family=str(row["family"]),
                label=str(row["label"]),
                description=str(row["description"]),
            )
            result[entry.definition] = entry
            result.setdefault(entry.canonical_id, entry)
        return result

    def get_narrative_sections(
        self,
        case_id: str,
        *,
        self_reported_only: bool = False,
        family_hints: list[str] | None = None,
    ) -> list[AdaptedNarrativeSection]:
        clauses = ["case_id = ?"]
        params: list[object] = [case_id]
        if self_reported_only:
            clauses.append("is_self_reported = 1")
        if family_hints:
            placeholders = ",".join("?" for _ in family_hints)
            clauses.append(f"family_hint IN ({placeholders})")
            params.extend(family_hints)
        sql = (
            "SELECT section_slug, heading, family_hint, is_self_reported, content "
            f"FROM patient_narrative_sections WHERE {' AND '.join(clauses)} ORDER BY id ASC"
        )
        rows = self._conn.execute(sql, params).fetchall()
        return [
            AdaptedNarrativeSection(
                section_slug=str(r["section_slug"]),
                heading=str(r["heading"]),
                family_hint=str(r["family_hint"]),
                is_self_reported=bool(r["is_self_reported"]),
                content=str(r["content"]),
            )
            for r in rows
        ]

    def _active_clause(self, alias: str = "pf") -> str:
        return (
            f"{alias}.export_status = 'active' "
            f"AND {alias}.superseded_at IS NULL "
            f"AND NOT EXISTS ("
            f"  SELECT 1 FROM patient_facts newer "
            f"  WHERE newer.case_id = {alias}.case_id "
            f"    AND newer.export_status = 'active' "
            f"    AND newer.superseded_at IS NULL "
            f"    AND newer.supersedes_fact_alias = {alias}.fact_alias"
            f")"
        )

    def query_facts(
        self,
        case_id: str,
        *,
        families: list[str] | None = None,
        canonical_ids: list[str] | None = None,
        canonical_prefix: str | None = None,
        evaluation_status: str | None = "success",
        active_only: bool = True,
        occurred_since: str | None = None,
        occurred_until: str | None = None,
        include_details: bool = True,
        limit: int | None = None,
    ) -> list[AdaptedFact]:
        clauses = ["pf.case_id = ?"]
        params: list[object] = [case_id]
        if active_only:
            clauses.append(self._active_clause("pf"))
        if evaluation_status is not None:
            clauses.append("pf.evaluation_status = ?")
            params.append(evaluation_status)
        if families:
            placeholders = ",".join("?" for _ in families)
            clauses.append(f"pf.family IN ({placeholders})")
            params.extend(families)
        if canonical_ids:
            placeholders = ",".join("?" for _ in canonical_ids)
            clauses.append(f"pf.canonical_id IN ({placeholders})")
            params.extend(canonical_ids)
        if canonical_prefix:
            clauses.append("pf.canonical_id LIKE ?")
            params.append(f"{canonical_prefix}%")
        if occurred_since:
            clauses.append("pf.occurred_to >= ?")
            params.append(occurred_since)
        if occurred_until:
            clauses.append("pf.occurred_from <= ?")
            params.append(occurred_until)

        sql = (
            "SELECT pf.* FROM patient_facts pf "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY pf.occurred_to DESC, pf.occurred_from DESC, pf.source_index DESC"
        )
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        if not rows:
            return []

        evidence_by_alias: dict[str, list[AdaptedEvidence]] = {}
        comparisons_by_alias: dict[str, list[AdaptedComparison]] = {}
        if include_details:
            aliases = [str(r["fact_alias"]) for r in rows]
            placeholders = ",".join("?" for _ in aliases)
            ev_rows = self._conn.execute(
                f"SELECT * FROM fact_evidence WHERE case_id = ? AND fact_alias IN ({placeholders}) ORDER BY id ASC",
                [case_id, *aliases],
            ).fetchall()
            for ev in ev_rows:
                evidence_by_alias.setdefault(str(ev["fact_alias"]), []).append(
                    AdaptedEvidence(
                        evidence_alias=str(ev["evidence_alias"]),
                        source_type=str(ev["source_type"]),
                        role=str(ev["role"]),
                        occurred_at=str(ev["occurred_at"]),
                    )
                )
            comp_rows = self._conn.execute(
                f"SELECT * FROM fact_comparisons WHERE case_id = ? AND fact_alias IN ({placeholders}) ORDER BY id ASC",
                [case_id, *aliases],
            ).fetchall()
            for comp in comp_rows:
                comparisons_by_alias.setdefault(str(comp["fact_alias"]), []).append(
                    AdaptedComparison(
                        kind=str(comp["kind"]),
                        target=float(comp["target"]) if comp["target"] is not None else None,
                        delta=float(comp["delta"]) if comp["delta"] is not None else None,
                        unit=str(comp["unit"]) if comp["unit"] is not None else None,
                        target_source=(
                            str(comp["target_source"])
                            if comp["target_source"] is not None
                            else None
                        ),
                    )
                )

        return [
            AdaptedFact(
                case_id=str(r["case_id"]),
                fact_alias=str(r["fact_alias"]),
                source_index=int(r["source_index"]),
                family=str(r["family"]),
                collection_kind=str(r["collection_kind"]),
                definition=str(r["definition"]),
                canonical_id=str(r["canonical_id"]),
                definition_version=str(r["definition_version"]),
                evaluation_key=str(r["evaluation_key"]),
                evaluation_status=str(r["evaluation_status"]),
                value_type=str(r["value_type"]) if r["value_type"] is not None else None,
                amount=float(r["amount"]) if r["amount"] is not None else None,
                unit=str(r["unit"]) if r["unit"] is not None else None,
                code_system=str(r["code_system"]) if r["code_system"] is not None else None,
                code=str(r["code"]) if r["code"] is not None else None,
                display_text=str(r["display_text"]) if r["display_text"] is not None else None,
                narrative_sections=json.loads(str(r["narrative_sections_json"])),
                clinical_attributes=json.loads(str(r["clinical_attributes_json"])),
                truncated=bool(r["truncated"]),
                occurred_from=str(r["occurred_from"]),
                occurred_to=str(r["occurred_to"]),
                recorded_at=str(r["recorded_at"]),
                valid_from=str(r["valid_from"]),
                valid_until=str(r["valid_until"]) if r["valid_until"] is not None else None,
                export_status=str(r["export_status"]),
                superseded_at=(
                    str(r["superseded_at"]) if r["superseded_at"] is not None else None
                ),
                supersedes_fact_alias=(
                    str(r["supersedes_fact_alias"])
                    if r["supersedes_fact_alias"] is not None
                    else None
                ),
                supersede_reason=(
                    str(r["supersede_reason"])
                    if r["supersede_reason"] is not None
                    else None
                ),
                engine_version=str(r["engine_version"]),
                missing_reasons=json.loads(str(r["missing_reasons_json"])),
                source_issues=json.loads(str(r["source_issues_json"])),
                evidence=evidence_by_alias.get(str(r["fact_alias"]), []),
                comparisons=comparisons_by_alias.get(str(r["fact_alias"]), []),
            )
            for r in rows
        ]

    def query_coded_history(
        self,
        case_id: str,
        code_prefixes: tuple[str, ...] | list[str],
    ) -> list[AdaptedFact]:
        """Her ICD kodunun en güncel aktif tanı satırı.

        Kod ön eki yoksa hiçbir satır dönmez. Boş ön ek, tüm tanıları seçmek
        anlamına gelmez.
        """
        prefixes = tuple(prefix.upper() for prefix in code_prefixes)
        rows = (
            self.query_facts(
                case_id,
                families=["diagnosis"],
                canonical_ids=["diagnosis.recorded-item"],
                evaluation_status="success",
                active_only=True,
                include_details=True,
            )
            if prefixes
            else []
        )
        coded_rows = [
            fact
            for fact in rows
            if (fact.code or "").strip()
        ]
        chosen: list[AdaptedFact] = []
        seen: set[str] = set()
        for fact in coded_rows:
            code = (fact.code or "").upper()
            if code in seen:
                continue
            if not prefixes or not code.startswith(prefixes):
                continue
            seen.add(code)
            chosen.append(fact)
        # #region agent log
        try:
            import json as _json
            import time as _time

            all_codes = []
            seen_all: set[str] = set()
            for fact in coded_rows:
                code = (fact.code or "").upper()
                if code in seen_all:
                    continue
                seen_all.add(code)
                all_codes.append(code)
            with open(
                r"c:\Projects\medical-rag-local\.cursor\debug-36fe44.log",
                "a",
                encoding="utf-8",
            ) as _fh:
                _fh.write(
                    _json.dumps(
                        {
                            "sessionId": "36fe44",
                            "hypothesisId": "B",
                            "location": "fact_repository.py:query_coded_history",
                            "message": "coded history filter",
                            "data": {
                                "caseId": case_id,
                                "prefixes": list(prefixes),
                                "filterApplied": bool(prefixes),
                                "distinctCodedCount": len(all_codes),
                                "chosenCount": len(chosen),
                                "chosenCodes": [fact.code for fact in chosen],
                                "iCodes": [code for code in all_codes if code.startswith("I")],
                                "e0Codes": [code for code in all_codes if code.startswith("E0")],
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
        return chosen

    def query_same_day_context(
        self,
        case_id: str,
        days: set[str],
        *,
        limit: int = 8,
    ) -> list[AdaptedFact]:
        """Seçilen tanı günlerine düşen muayene, görüntüleme ve patoloji satırları."""
        if not days:
            return []
        rows = self.query_facts(
            case_id,
            families=["visit", "imaging", "pathology"],
            evaluation_status="success",
            active_only=True,
            include_details=False,
        )
        matched: list[AdaptedFact] = []
        seen: set[str] = set()
        for fact in rows:
            day_from = (fact.occurred_from or "")[:10]
            day_to = (fact.occurred_to or "")[:10]
            if day_from not in days and day_to not in days:
                continue
            if fact.fact_alias in seen:
                continue
            seen.add(fact.fact_alias)
            matched.append(fact)
            if len(matched) >= limit:
                break
        return matched

    def list_active_canonical_ids(
        self,
        case_id: str,
        *,
        families: list[str] | None = None,
        evaluation_status: str = "success",
    ) -> list[str]:
        clauses = ["pf.case_id = ?", self._active_clause("pf"), "pf.evaluation_status = ?"]
        params: list[object] = [case_id, evaluation_status]
        if families:
            placeholders = ",".join("?" for _ in families)
            clauses.append(f"pf.family IN ({placeholders})")
            params.extend(families)
        rows = self._conn.execute(
            f"SELECT DISTINCT pf.canonical_id FROM patient_facts pf WHERE {' AND '.join(clauses)} ORDER BY pf.canonical_id ASC",
            params,
        ).fetchall()
        return [str(r["canonical_id"]) for r in rows]

    def compute_numeric_stats(
        self,
        case_id: str,
        canonical_id: str,
        *,
        occurred_since: str | None = None,
        occurred_until: str | None = None,
    ) -> NumericSeriesSummary | None:
        """Aktif sayısal seri üzerinde SQL/Python ile kesin istatistik ve son değer hesaplar."""
        facts = self.query_facts(
            case_id,
            canonical_ids=[canonical_id],
            evaluation_status="success",
            active_only=True,
            occurred_since=occurred_since,
            occurred_until=occurred_until,
            include_details=False,
        )
        numeric_facts = [f for f in facts if f.amount is not None]
        if not numeric_facts:
            return None

        latest = numeric_facts[0]
        amounts = [float(f.amount) for f in numeric_facts if f.amount is not None]
        earliest_from = min(f.occurred_from for f in numeric_facts)
        return NumericSeriesSummary(
            case_id=case_id,
            canonical_id=canonical_id,
            unit=latest.unit,
            sample_count=len(amounts),
            min_amount=min(amounts),
            max_amount=max(amounts),
            avg_amount=round(sum(amounts) / len(amounts), 4),
            latest_amount=float(latest.amount),  # type: ignore[arg-type]
            latest_fact_alias=latest.fact_alias,
            latest_evaluation_key=latest.evaluation_key,
            latest_occurred_from=latest.occurred_from,
            latest_occurred_to=latest.occurred_to,
            latest_recorded_at=latest.recorded_at,
            earliest_occurred_from=earliest_from,
        )

    def summarize_missing_data(
        self,
        case_id: str,
        *,
        families: list[str] | None = None,
        canonical_prefix: str | None = None,
    ) -> list[MissingDataGroupSummary]:
        """`data-required` satırları tanım ve eksiklik nedenlerine göre gruplar."""
        missing_facts = self.query_facts(
            case_id,
            families=families,
            canonical_prefix=canonical_prefix,
            evaluation_status="data-required",
            active_only=True,
            include_details=False,
        )
        groups: dict[tuple[str, str, str, tuple[str, ...]], list[AdaptedFact]] = {}
        for item in missing_facts:
            key = (
                item.family,
                item.canonical_id,
                item.definition_version,
                tuple(sorted(item.missing_reasons)),
            )
            groups.setdefault(key, []).append(item)

        summaries: list[MissingDataGroupSummary] = []
        for (family, canonical_id, version, reasons), items in sorted(groups.items()):
            summaries.append(
                MissingDataGroupSummary(
                    family=family,
                    canonical_id=canonical_id,
                    definition_version=version,
                    missing_reasons=list(reasons),
                    row_count=len(items),
                    earliest_occurred_from=min(f.occurred_from for f in items),
                    latest_occurred_to=max(f.occurred_to for f in items),
                    sample_fact_aliases=[f.fact_alias for f in items[:3]],
                )
            )
        return summaries
