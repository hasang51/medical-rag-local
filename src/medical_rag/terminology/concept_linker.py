"""Türkçe/İngilizce klinik ifadeleri aktif SNOMED CT IPS kavramlarına bağlayan modül.

Tasarım ilkeleri:
1. Yalnızca SQLite `snomed_concepts` tablosunda doğrulanmış aktif (`active = '1'`)
   kavramları döndürür; veritabanında bulunmayan kavram uydurulmaz.
2. İlişki türleri (`type_id` + `type_label`: `Is a`, `Finding site`, `Associated morphology`,
   `Interprets`, `Has active ingredient`, `Due to` vb.) açıkça korunur.
3. SNOMED CT IPS olasılıksal bir hastalık-semptom tanı motoru olarak kullanılmaz;
   çıktıda tanı olasılığı üretilmez, yalnız ontolojik tanım ve CCO aile yönlendirmesi yapılır.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

from medical_rag.rag.text import fold, tokenize_clinical

IS_A_TYPE_ID = "116680003"
ONTOLOGICAL_NOTICE = (
    "SNOMED CT IPS yapısal kavram ilişkisi; hastalık olasılığı veya tanı kanıtı değildir."
)

# Öncelikli klinik anlamsal etiketler (metadata kavramlarının önüne geçer)
_CLINICAL_SEMANTIC_TAGS = frozenset(
    {
        "finding",
        "disorder",
        "observable entity",
        "substance",
        "clinical drug",
        "medicinal product",
        "procedure",
        "situation",
        "morphologic abnormality",
    }
)


@dataclass(frozen=True)
class SnomedRelationEdge:
    direction: str  # "outgoing" | "incoming_subtype"
    type_id: str
    type_label: str
    target_concept_id: str
    target_preferred_term: str
    target_fsn: str
    relationship_group: int


@dataclass(frozen=True)
class LinkedConcept:
    concept_id: str
    preferred_term: str
    fsn: str
    semantic_tag: str
    in_ips_refset: bool
    matched_phrase: str
    match_source: str  # "tr_clinical_lexicon" | "en_exact_description" | "en_fts_description"
    synonyms: list[str]
    relationships: list[SnomedRelationEdge]
    cco_families: list[str] = field(default_factory=list)
    ontological_notice: str = ONTOLOGICAL_NOTICE


@dataclass(frozen=True)
class _TrLexiconRule:
    pattern: re.Pattern[str]
    label: str
    concept_id: str
    cco_families: tuple[str, ...]


# Tüm concept_id değerleri SnomedCT_IPS_Terminology_2024 Snapshot üzerinde doğrulanmıştır.
_TR_CLINICAL_RULES: tuple[_TrLexiconRule, ...] = (
    _TrLexiconRule(
        re.compile(r"gerilim\s+tipi\s+baş\s*ağr"),
        "gerilim tipi baş ağrısı",
        "398057008",
        ("sleep", "cardio", "wellness", "diagnosis", "medication"),
    ),
    _TrLexiconRule(
        re.compile(r"\bmigren"),
        "migren",
        "37796009",
        ("sleep", "cardio", "diagnosis", "medication"),
    ),
    _TrLexiconRule(
        re.compile(r"baş\s*ağr|başım\s*ağr|başımda\s*ağr|\bsefalji"),
        "baş ağrısı",
        "25064002",
        ("sleep", "cardio", "vitals", "hydration", "diagnosis", "medication"),
    ),
    _TrLexiconRule(
        re.compile(r"baş\s*dönme|başım\s*dön|\bsersemlik|\bvertigo"),
        "baş dönmesi",
        "404640003",
        ("vitals", "cardio", "hydration", "lab", "medication"),
    ),
    _TrLexiconRule(
        re.compile(r"\byorgun|\bhalsiz|\bbitkin"),
        "yorgunluk / halsizlik",
        "84229001",
        ("sleep", "cardio", "recovery", "lab", "activity"),
    ),
    _TrLexiconRule(
        re.compile(r"\buykusuz|uyuyam|uyku\s+bozuk"),
        "uykusuzluk",
        "193462001",
        ("sleep", "cardio", "wellness"),
    ),
    _TrLexiconRule(
        re.compile(r"\bçarpıntı|kalbim\s+çarp"),
        "çarpıntı",
        "80313002",
        ("cardio", "vitals", "lab", "medication"),
    ),
    _TrLexiconRule(
        re.compile(r"\btaşikardi|nabzım\s+yüksek|kalbim\s+hızlı"),
        "taşikardi",
        "3424008",
        ("cardio", "vitals"),
    ),
    _TrLexiconRule(
        re.compile(r"\bbradikardi|nabzım\s+düşük"),
        "bradikardi",
        "48867003",
        ("cardio", "sleep"),
    ),
    _TrLexiconRule(
        re.compile(r"nefes\s+darlığ|soluk\s+darlığ|\bdispne"),
        "nefes darlığı",
        "267036007",
        ("oxygen", "recovery", "cardio", "diagnosis"),
    ),
    _TrLexiconRule(
        re.compile(r"\böksür"),
        "öksürük",
        "49727002",
        ("recovery", "oxygen", "diagnosis", "medication"),
    ),
    _TrLexiconRule(
        re.compile(r"\bateşim|\byüksek\s+ateş|\bateş\b"),
        "ateş",
        "386661006",
        ("recovery", "cardio", "diagnosis", "lab"),
    ),
    _TrLexiconRule(
        re.compile(r"\bbulantı|midem\s+bulan"),
        "mide bulantısı",
        "422587007",
        ("hydration", "medication", "diagnosis", "lab"),
    ),
    _TrLexiconRule(
        re.compile(r"karın\s+ağr|karnım\s+ağr"),
        "karın ağrısı",
        "21522001",
        ("diagnosis", "lab", "visit", "imaging"),
    ),
    _TrLexiconRule(
        re.compile(r"bel\s+ağr|belim\s+ağr"),
        "bel ağrısı",
        "279039007",
        ("activity", "diagnosis", "imaging", "medication"),
    ),
    _TrLexiconRule(
        re.compile(r"\bhipertansiyon|\btansiyon|kan\s+basınc"),
        "hipertansiyon / kan basıncı",
        "38341003",
        ("vitals", "cardio", "medication", "diagnosis"),
    ),
    _TrLexiconRule(
        re.compile(r"\bdiyabet|şeker\s+hastalığ|kan\s+şeker|\bhba1c"),
        "diyabet",
        "73211009",
        ("glucose", "lab", "medication", "diagnosis"),
    ),
    _TrLexiconRule(
        re.compile(r"\banemi|\bkansızlık|\bhemoglobin"),
        "anemi",
        "271737000",
        ("lab", "diagnosis", "medication"),
    ),
    _TrLexiconRule(
        re.compile(r"d\s+vitamin"),
        "D vitamini eksikliği",
        "34713006",
        ("lab", "medication", "diagnosis"),
    ),
    _TrLexiconRule(
        re.compile(r"\bhipotiroid|\btsh\b"),
        "hipotiroidi",
        "40930008",
        ("lab", "medication", "diagnosis"),
    ),
    _TrLexiconRule(
        re.compile(r"\bhipertiroid"),
        "hipertiroidi",
        "34486009",
        ("lab", "medication", "diagnosis"),
    ),
    _TrLexiconRule(
        re.compile(r"\btiroit|\btiroid"),
        "tiroit bezi hastalığı",
        "14304000",
        ("lab", "medication", "diagnosis"),
    ),
    _TrLexiconRule(
        re.compile(r"\bkolesterol|\bhiperkolesterolemi|\bldl\b"),
        "hiperkolesterolemi",
        "13644009",
        ("lab", "medication", "diagnosis"),
    ),
    _TrLexiconRule(
        re.compile(r"\bastım"),
        "astım",
        "195967001",
        ("oxygen", "recovery", "diagnosis", "medication"),
    ),
    _TrLexiconRule(
        re.compile(r"alerjik\s+rinit|saman\s+nezle"),
        "alerjik rinit",
        "61582004",
        ("diagnosis", "medication"),
    ),
    _TrLexiconRule(
        re.compile(r"\bstres"),
        "stres",
        "73595000",
        ("wellness", "sleep", "cardio"),
    ),
)

_SEMANTIC_TAG_DEFAULT_FAMILIES: dict[str, tuple[str, ...]] = {
    "finding": ("diagnosis", "visit", "vitals", "sleep", "cardio"),
    "disorder": ("diagnosis", "medication", "lab", "visit"),
    "observable entity": ("vitals", "lab", "cardio", "sleep"),
    "substance": ("medication", "lab"),
    "clinical drug": ("medication",),
    "medicinal product": ("medication",),
    "procedure": ("visit", "imaging", "lab"),
}


class ConceptLinker:
    """Sorgudaki klinik terimleri doğrulanmış SNOMED CT IPS kavramlarına bağlar."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.row_factory = sqlite3.Row

    def get_concept(
        self,
        concept_id: str,
        *,
        matched_phrase: str = "",
        match_source: str = "direct_id",
        cco_families: list[str] | None = None,
        max_subtypes: int = 5,
    ) -> LinkedConcept | None:
        row = self._conn.execute(
            "SELECT * FROM snomed_concepts WHERE concept_id = ?",
            (concept_id,),
        ).fetchone()
        if row is None:
            return None

        desc_rows = self._conn.execute(
            """
            SELECT term, type_id FROM snomed_descriptions
            WHERE concept_id = ?
            ORDER BY type_id DESC, LENGTH(term) ASC, term ASC
            """,
            (concept_id,),
        ).fetchall()
        synonyms: list[str] = []
        for d in desc_rows:
            term = str(d["term"])
            if str(d["type_id"]) != "900000000000003001" and term not in synonyms:
                synonyms.append(term)

        out_rows = self._conn.execute(
            """
            SELECT r.type_id, r.type_label, r.destination_id, r.relationship_group,
                   c.preferred_term, c.fsn
            FROM snomed_relationships r
            JOIN snomed_concepts c ON c.concept_id = r.destination_id
            WHERE r.source_id = ?
            ORDER BY r.relationship_group ASC, r.type_id ASC, c.preferred_term ASC
            """,
            (concept_id,),
        ).fetchall()
        edges: list[SnomedRelationEdge] = [
            SnomedRelationEdge(
                direction="outgoing",
                type_id=str(r["type_id"]),
                type_label=str(r["type_label"]),
                target_concept_id=str(r["destination_id"]),
                target_preferred_term=str(r["preferred_term"]),
                target_fsn=str(r["fsn"]),
                relationship_group=int(r["relationship_group"]),
            )
            for r in out_rows
        ]

        if max_subtypes > 0:
            in_rows = self._conn.execute(
                """
                SELECT r.type_id, r.type_label, r.source_id, r.relationship_group,
                       c.preferred_term, c.fsn
                FROM snomed_relationships r
                JOIN snomed_concepts c ON c.concept_id = r.source_id
                WHERE r.destination_id = ? AND r.type_id = ?
                ORDER BY c.in_ips_refset DESC, LENGTH(c.preferred_term) ASC, c.preferred_term ASC
                LIMIT ?
                """,
                (concept_id, IS_A_TYPE_ID, max_subtypes),
            ).fetchall()
            for r in in_rows:
                edges.append(
                    SnomedRelationEdge(
                        direction="incoming_subtype",
                        type_id=str(r["type_id"]),
                        type_label="Has subtype (inverse Is a)",
                        target_concept_id=str(r["source_id"]),
                        target_preferred_term=str(r["preferred_term"]),
                        target_fsn=str(r["fsn"]),
                        relationship_group=int(r["relationship_group"]),
                    )
                )

        sem_tag = str(row["semantic_tag"])
        resolved_families = (
            cco_families
            if cco_families is not None
            else list(_SEMANTIC_TAG_DEFAULT_FAMILIES.get(sem_tag, ("diagnosis", "visit")))
        )

        return LinkedConcept(
            concept_id=str(row["concept_id"]),
            preferred_term=str(row["preferred_term"]),
            fsn=str(row["fsn"]),
            semantic_tag=sem_tag,
            in_ips_refset=bool(row["in_ips_refset"]),
            matched_phrase=matched_phrase or str(row["preferred_term"]),
            match_source=match_source,
            synonyms=synonyms[:8],
            relationships=edges,
            cco_families=resolved_families,
        )

    def link_text(self, text: str, *, max_concepts: int = 3) -> list[LinkedConcept]:
        """Metindeki Türkçe veya İngilizce klinik ifadeleri aktif SNOMED kavramlarına bağlar."""
        folded = fold(text)
        linked: list[LinkedConcept] = []
        seen_ids: set[str] = set()

        # Aşama 1: Küratörlü Türkçe semptom ve klinik kavram kuralları
        for rule in _TR_CLINICAL_RULES:
            if rule.pattern.search(folded) and rule.concept_id not in seen_ids:
                concept = self.get_concept(
                    rule.concept_id,
                    matched_phrase=rule.label,
                    match_source="tr_clinical_lexicon",
                    cco_families=list(rule.cco_families),
                )
                if concept is not None:
                    seen_ids.add(concept.concept_id)
                    linked.append(concept)
                    if len(linked) >= max_concepts:
                        return linked

        # Aşama 2: İngilizce/uluslararası tam terim ve n-gram eşleşmesi (1..3 kelime)
        tokens = [t for t in tokenize_clinical(text) if len(t) >= 3 and t.isascii()]
        if tokens and len(linked) < max_concepts:
            candidate_phrases: list[str] = []
            for n in (3, 2, 1):
                for idx in range(len(tokens) - n + 1):
                    phrase = " ".join(tokens[idx : idx + n])
                    if phrase not in candidate_phrases:
                        candidate_phrases.append(phrase)

            for phrase in candidate_phrases:
                exact_rows = self._conn.execute(
                    """
                    SELECT c.concept_id, c.semantic_tag, c.in_ips_refset
                    FROM snomed_descriptions d
                    JOIN snomed_concepts c ON c.concept_id = d.concept_id
                    WHERE d.term_folded = ?
                    ORDER BY c.in_ips_refset DESC, LENGTH(c.preferred_term) ASC
                    LIMIT 5
                    """,
                    (phrase,),
                ).fetchall()
                for r in exact_rows:
                    cid = str(r["concept_id"])
                    tag = str(r["semantic_tag"])
                    if cid in seen_ids or tag not in _CLINICAL_SEMANTIC_TAGS:
                        continue
                    concept = self.get_concept(
                        cid,
                        matched_phrase=phrase,
                        match_source="en_exact_description",
                    )
                    if concept is not None:
                        seen_ids.add(cid)
                        linked.append(concept)
                        break
                if len(linked) >= max_concepts:
                    return linked

            # Aşama 3: FTS5 çok-kelimeli ifade araması (yalnız en az 2 ASCII terim varsa)
            if len(linked) == 0 and len(tokens) >= 2:
                fts_query = " AND ".join(f'"{tok}"' for tok in tokens[:4])
                fts_rows = self._conn.execute(
                    """
                    SELECT c.concept_id, c.semantic_tag
                    FROM snomed_descriptions_fts f
                    JOIN snomed_concepts c ON c.concept_id = f.concept_id
                    WHERE snomed_descriptions_fts MATCH ?
                    ORDER BY c.in_ips_refset DESC, LENGTH(c.preferred_term) ASC
                    LIMIT 5
                    """,
                    (fts_query,),
                ).fetchall()
                for r in fts_rows:
                    cid = str(r["concept_id"])
                    tag = str(r["semantic_tag"])
                    if cid in seen_ids or tag not in _CLINICAL_SEMANTIC_TAGS:
                        continue
                    concept = self.get_concept(
                        cid,
                        matched_phrase=" ".join(tokens[:4]),
                        match_source="en_fts_description",
                    )
                    if concept is not None:
                        seen_ids.add(cid)
                        linked.append(concept)
                        if len(linked) >= max_concepts:
                            return linked

        return linked
