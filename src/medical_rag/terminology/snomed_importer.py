"""SNOMED CT IPS 2024 RF2 Snapshot dosyalarını SQLite tablolarına aktaran modül.

Yalnızca `active = '1'` kayıtları kabul eder. İlişki türlerini (`typeId` ve FSN etiketi)
ve İngilizce dil refset kabul edilebilirlik bilgisini (`US`/`GB`, `Preferred`/`Acceptable`)
korur. Pasif kavram veya doğrulanmamış ilişki eklenmez.
"""

from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from medical_rag.rag.text import fold

FSN_TYPE_ID = "900000000000003001"
SYNONYM_TYPE_ID = "900000000000013009"
US_ENGLISH_REFSET_ID = "900000000000509007"
GB_ENGLISH_REFSET_ID = "900000000000508004"
PREFERRED_ACCEPTABILITY_ID = "900000000000548007"
IPS_SIMPLE_REFSET_ID = "816080008"


@dataclass(frozen=True)
class SnomedImportCounts:
    active_concepts: int
    active_descriptions: int
    active_relationships: int
    ips_refset_members: int
    distinct_relationship_types: int


_SNOMED_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS snomed_concepts (
    concept_id TEXT PRIMARY KEY,
    effective_time TEXT NOT NULL,
    module_id TEXT NOT NULL,
    definition_status_id TEXT NOT NULL,
    fsn TEXT NOT NULL,
    preferred_term TEXT NOT NULL,
    semantic_tag TEXT NOT NULL,
    in_ips_refset INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snomed_concepts_tag
    ON snomed_concepts (semantic_tag, in_ips_refset);

CREATE TABLE IF NOT EXISTS snomed_descriptions (
    description_id TEXT PRIMARY KEY,
    concept_id TEXT NOT NULL,
    language_code TEXT NOT NULL,
    type_id TEXT NOT NULL,
    term TEXT NOT NULL,
    term_folded TEXT NOT NULL,
    us_acceptability_id TEXT,
    gb_acceptability_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_snomed_desc_concept
    ON snomed_descriptions (concept_id, type_id);
CREATE INDEX IF NOT EXISTS idx_snomed_desc_folded
    ON snomed_descriptions (term_folded);

CREATE VIRTUAL TABLE IF NOT EXISTS snomed_descriptions_fts USING fts5(
    concept_id UNINDEXED,
    description_id UNINDEXED,
    term,
    term_folded
);

CREATE TABLE IF NOT EXISTS snomed_relationships (
    relationship_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    destination_id TEXT NOT NULL,
    relationship_group INTEGER NOT NULL,
    type_id TEXT NOT NULL,
    type_label TEXT NOT NULL,
    characteristic_type_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snomed_rel_source
    ON snomed_relationships (source_id, type_id);
CREATE INDEX IF NOT EXISTS idx_snomed_rel_dest
    ON snomed_relationships (destination_id, type_id);
"""


def _extract_semantic_tag(fsn: str) -> tuple[str, str]:
    """FSN sonundaki anlamsal etiketi ayırır; ör. `'Headache (finding)' -> ('Headache', 'finding')`."""
    if fsn.endswith(")") and "(" in fsn:
        idx = fsn.rfind("(")
        base = fsn[:idx].strip()
        tag = fsn[idx + 1 : -1].strip()
        return base, tag
    return fsn, ""


def _clean_attribute_label(fsn: str) -> str:
    base, _ = _extract_semantic_tag(fsn)
    return base


def _find_single_rf2_file(directory: Path, pattern: str) -> Path:
    matches = sorted(directory.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"SNOMED RF2 dosyası bulunamadı: {directory / pattern}")
    return matches[0]


class SnomedImporter:
    """SNOMED CT IPS RF2 Snapshot dosyalarını SQLite veritabanına aktarır."""

    def __init__(self, conn_or_path: sqlite3.Connection | Path) -> None:
        if isinstance(conn_or_path, sqlite3.Connection):
            self._conn = conn_or_path
            self._owns_conn = False
        else:
            if str(conn_or_path) != ":memory:":
                conn_or_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(conn_or_path), check_same_thread=False)
            self._owns_conn = True
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.executescript(_SNOMED_SCHEMA_SQL)

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    def close(self) -> None:
        if self._owns_conn:
            self._conn.close()

    def counts(self) -> SnomedImportCounts:
        c_cnt = int(
            self._conn.execute("SELECT COUNT(*) FROM snomed_concepts").fetchone()[0]
        )
        d_cnt = int(
            self._conn.execute("SELECT COUNT(*) FROM snomed_descriptions").fetchone()[0]
        )
        r_cnt = int(
            self._conn.execute("SELECT COUNT(*) FROM snomed_relationships").fetchone()[0]
        )
        ips_cnt = int(
            self._conn.execute(
                "SELECT COUNT(*) FROM snomed_concepts WHERE in_ips_refset = 1"
            ).fetchone()[0]
        )
        t_cnt = int(
            self._conn.execute(
                "SELECT COUNT(DISTINCT type_id) FROM snomed_relationships"
            ).fetchone()[0]
        )
        return SnomedImportCounts(
            active_concepts=c_cnt,
            active_descriptions=d_cnt,
            active_relationships=r_cnt,
            ips_refset_members=ips_cnt,
            distinct_relationship_types=t_cnt,
        )

    def ensure_imported(self, snomed_package_dir: Path) -> SnomedImportCounts:
        """SNOMED tabloları doluysa yeniden aktarmaz; boşsa RF2 Snapshot'tan yükler."""
        existing = self.counts()
        if existing.active_concepts > 0 and existing.active_descriptions > 0:
            return existing
        if not snomed_package_dir.exists():
            return existing
        return self.import_snapshot(snomed_package_dir)

    def import_snapshot(self, snomed_package_dir: Path) -> SnomedImportCounts:
        term_dir = snomed_package_dir / "Snapshot" / "Terminology"
        refset_dir = snomed_package_dir / "Snapshot" / "Refset"

        concept_file = _find_single_rf2_file(term_dir, "sct2_Concept_IPSSnapshot_*.txt")
        desc_file = _find_single_rf2_file(
            term_dir, "sct2_Description_IPSSnapshot-en_*.txt"
        )
        rel_file = _find_single_rf2_file(
            term_dir, "sct2_Relationship_IPSSnapshot_*.txt"
        )
        lang_file = _find_single_rf2_file(
            refset_dir / "Language", "der2_cRefset_IPSLanguageSnapshot-en_*.txt"
        )
        ips_file = _find_single_rf2_file(
            refset_dir / "Content", "der2_Refset_IPSSimpleSnapshot_*.txt"
        )

        # 1. IPS Simple Refset aktif üyeleri
        ips_members: set[str] = set()
        with ips_file.open("r", encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                if row["active"] == "1" and row["refsetId"] == IPS_SIMPLE_REFSET_ID:
                    ips_members.add(row["referencedComponentId"])

        # 2. Aktif kavramlar
        raw_concepts: dict[str, tuple[str, str, str]] = {}
        with concept_file.open("r", encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                if row["active"] == "1":
                    raw_concepts[row["id"]] = (
                        row["effectiveTime"],
                        row["moduleId"],
                        row["definitionStatusId"],
                    )

        # 3. Dil refset kabul edilebilirlikleri (descriptionId -> (us_acc, gb_acc))
        us_acc: dict[str, str] = {}
        gb_acc: dict[str, str] = {}
        with lang_file.open("r", encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                if row["active"] != "1":
                    continue
                desc_id = row["referencedComponentId"]
                refset_id = row["refsetId"]
                acc_id = row["acceptabilityId"]
                if refset_id == US_ENGLISH_REFSET_ID:
                    us_acc[desc_id] = acc_id
                elif refset_id == GB_ENGLISH_REFSET_ID:
                    gb_acc[desc_id] = acc_id

        # 4. Aktif açıklamalar (yalnız aktif kavramlara bağlı olanlar)
        fsn_by_concept: dict[str, str] = {}
        us_pref_by_concept: dict[str, str] = {}
        gb_pref_by_concept: dict[str, str] = {}
        first_syn_by_concept: dict[str, str] = {}
        description_rows: list[tuple[str, str, str, str, str, str, str | None, str | None]] = []

        with desc_file.open("r", encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                if row["active"] != "1":
                    continue
                cid = row["conceptId"]
                if cid not in raw_concepts:
                    continue
                did = row["id"]
                type_id = row["typeId"]
                term = row["term"]
                term_folded = fold(term)
                u_acc = us_acc.get(did)
                g_acc = gb_acc.get(did)

                if type_id == FSN_TYPE_ID:
                    fsn_by_concept[cid] = term
                elif type_id == SYNONYM_TYPE_ID:
                    first_syn_by_concept.setdefault(cid, term)
                    if u_acc == PREFERRED_ACCEPTABILITY_ID:
                        us_pref_by_concept[cid] = term
                    if g_acc == PREFERRED_ACCEPTABILITY_ID:
                        gb_pref_by_concept[cid] = term

                description_rows.append(
                    (
                        did,
                        cid,
                        row["languageCode"],
                        type_id,
                        term,
                        term_folded,
                        u_acc,
                        g_acc,
                    )
                )

        concept_rows: list[tuple[str, str, str, str, str, str, str, int]] = []
        for cid, (eff_time, mod_id, def_status) in raw_concepts.items():
            fsn = fsn_by_concept.get(cid, first_syn_by_concept.get(cid, cid))
            base_term, sem_tag = _extract_semantic_tag(fsn)
            pref = (
                us_pref_by_concept.get(cid)
                or gb_pref_by_concept.get(cid)
                or first_syn_by_concept.get(cid)
                or base_term
            )
            concept_rows.append(
                (
                    cid,
                    eff_time,
                    mod_id,
                    def_status,
                    fsn,
                    pref,
                    sem_tag,
                    1 if cid in ips_members else 0,
                )
            )

        # 5. Aktif ilişkiler (sourceId, destinationId ve typeId aktif kavram olmalı)
        relationship_rows: list[tuple[str, str, str, int, str, str, str]] = []
        with rel_file.open("r", encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                if row["active"] != "1":
                    continue
                src_id = row["sourceId"]
                dst_id = row["destinationId"]
                type_id = row["typeId"]
                if (
                    src_id not in raw_concepts
                    or dst_id not in raw_concepts
                    or type_id not in raw_concepts
                ):
                    continue
                type_label = _clean_attribute_label(fsn_by_concept.get(type_id, type_id))
                relationship_rows.append(
                    (
                        row["id"],
                        src_id,
                        dst_id,
                        int(row["relationshipGroup"]),
                        type_id,
                        type_label,
                        row["characteristicTypeId"],
                    )
                )

        with self._conn:
            self._conn.execute("DELETE FROM snomed_relationships")
            self._conn.execute("DELETE FROM snomed_descriptions_fts")
            self._conn.execute("DELETE FROM snomed_descriptions")
            self._conn.execute("DELETE FROM snomed_concepts")

            self._conn.executemany(
                """
                INSERT INTO snomed_concepts (
                    concept_id, effective_time, module_id, definition_status_id,
                    fsn, preferred_term, semantic_tag, in_ips_refset
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                concept_rows,
            )
            self._conn.executemany(
                """
                INSERT INTO snomed_descriptions (
                    description_id, concept_id, language_code, type_id,
                    term, term_folded, us_acceptability_id, gb_acceptability_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                description_rows,
            )
            self._conn.executemany(
                """
                INSERT INTO snomed_descriptions_fts (
                    concept_id, description_id, term, term_folded
                ) VALUES (?, ?, ?, ?)
                """,
                [(d[1], d[0], d[4], d[5]) for d in description_rows],
            )
            self._conn.executemany(
                """
                INSERT INTO snomed_relationships (
                    relationship_id, source_id, destination_id, relationship_group,
                    type_id, type_label, characteristic_type_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                relationship_rows,
            )

        return self.counts()
