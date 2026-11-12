"""Geçmiş hastalık araması.

En yeni giyilebilir kayıtların tavanı eski kodlu tanıları düşürür. Bu operatör
soruyu bir organ veya sistem bölümüne bağlar ve o bölümdeki kodlu tanıları
olay zamanından bağımsız getirir. Vaka adına veya tek bir hastalığa kilitlenmez.

Kesin tanı sorgusunda kaynak, kodlu tanı satırı ve onu metin olarak destekleyen
kayıtlardır. Aynı takvim günü veya aynı vizit, tek başına ilgililik değildir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from medical_rag.rag.text import fold

_HISTORY_CUES = re.compile(
    r"daha önce|daha once|olmuş mu|olmus mu|geçirdim|gecirdim|"
    r"geçmiş|gecmis|öykü|oyku|öyküm|oykum"
)

@dataclass(frozen=True)
class HistoryConcept:
    """SNOMED CT IPS kavramı ve ona karşılık gelen ICD-10 kod ön ekleri.

    Kavram kimlikleri yerel IPS anlık görüntüsünde (20241216) doğrulanmıştır.
    Kod ön ekleri DSÖ ICD-10 2019 bloklarıdır; hasta adına kilitlenmez.
    """

    concept_id: str
    label: str
    code_prefixes: tuple[str, ...]
    support_terms: tuple[str, ...]


# Daha özel kavram, aynı kökü taşıyan genel kavramdan önce yazılır.
# Tiroid: E00–E07. Kalp: I01 ve I05–I09, I1–I5'in dışında kalan romatizmal bloktur.
_CHAPTERS: tuple[tuple[re.Pattern[str], HistoryConcept], ...] = (
    (
        re.compile(
            r"\bmide|\bgastr|reflü|reflu|ülser|ulser|özofaj|ozofaj|"
            r"\bsindirim|karın|karnım|bağırsak|bagirsak|bulantı|bulanti"
        ),
        HistoryConcept(
            "",
            "sindirim sistemi",
            ("K2", "K3"),
            ("mide", "gastr", "reflü", "reflu", "ülser", "ulser", "özofaj", "ozofaj", "peptik"),
        ),
    ),
    (
        re.compile(r"\bkalp|\bkardiy"),
        HistoryConcept(
            "56265001",
            "Heart disease",
            ("I01", "I05", "I06", "I07", "I08", "I09", "I1", "I2", "I3", "I4", "I5"),
            ("kalp", "kardiy", "kardiyo", "cardiac", "heart", "koroner", "miyokard"),
        ),
    ),
    (
        re.compile(r"hipertans"),
        HistoryConcept(
            "38341003",
            "Hypertensive disorder",
            ("I1",),
            ("hipertans", "hypertension", "tansiyon"),
        ),
    ),
    (
        re.compile(r"aritmi"),
        HistoryConcept(
            "698247007",
            "Cardiac arrhythmia",
            ("I4",),
            ("aritmi", "arrhythmia"),
        ),
    ),
    (
        re.compile(r"hipotiroid"),
        HistoryConcept(
            "40930008",
            "Hypothyroidism",
            ("E0",),
            ("hipotiroid", "tiroit", "tiroid", "thyroid", "tsh", "ft3", "ft4", "tiroksin"),
        ),
    ),
    (
        re.compile(r"hipertiroid"),
        HistoryConcept(
            "34486009",
            "Hyperthyroidism",
            ("E05",),
            ("hipertiroid", "tiroit", "tiroid", "thyroid", "tsh", "ft3", "ft4", "tiroksin"),
        ),
    ),
    (
        re.compile(r"tiroit|(?<!hipo)(?<!hiper)tiroid"),
        HistoryConcept(
            "14304000",
            "Disorder of thyroid gland",
            ("E0",),
            ("tiroit", "tiroid", "thyroid", "hipotiroid", "hipertiroid", "tsh", "ft3", "ft4", "tiroksin"),
        ),
    ),
    (
        re.compile(r"diyabet|şeker hastal|seker hastal"),
        HistoryConcept(
            "73211009",
            "Diabetes mellitus",
            ("E1",),
            ("diyabet", "diabet", "hba1c", "insulin", "insülin"),
        ),
    ),
    (
        re.compile(r"\bastım|\bastim|\bkoah|bronşit|bronsit"),
        HistoryConcept(
            "",
            "solunum",
            ("J4", "J45"),
            ("astım", "astim", "koah", "bronşit", "bronsit"),
        ),
    ),
    (
        re.compile(r"böbrek|bobrek|idrar yolu"),
        HistoryConcept(
            "",
            "üriner",
            ("N1", "N2", "N3"),
            ("böbrek", "bobrek", "idrar yolu"),
        ),
    ),
    (
        re.compile(r"\banemi|kansız|kansiz"),
        HistoryConcept("", "anemi", ("D5", "D6"), ("anemi", "kansız", "kansiz")),
    ),
    (
        re.compile(r"depres|anksiye|panik atak"),
        HistoryConcept(
            "",
            "duygudurum",
            ("F3", "F4"),
            ("depres", "anksiye", "panik atak"),
        ),
    ),
)


@dataclass(frozen=True)
class HistoryQuery:
    active: bool
    code_prefixes: tuple[str, ...] = ()
    concepts: tuple[HistoryConcept, ...] = ()

    @property
    def resolved(self) -> bool:
        return self.active and bool(self.code_prefixes)


def parse_history_query(folded_question: str) -> HistoryQuery:
    """Katlanmış soru geçmiş hastalık araması mı, hangi kod bölümünde?"""
    if not _HISTORY_CUES.search(folded_question):
        return HistoryQuery(active=False)
    prefixes: list[str] = []
    concepts: list[HistoryConcept] = []
    for pattern, concept in _CHAPTERS:
        if pattern.search(folded_question):
            concepts.append(concept)
            for prefix in concept.code_prefixes:
                if prefix not in prefixes:
                    prefixes.append(prefix)
    return HistoryQuery(
        active=True,
        code_prefixes=tuple(prefixes),
        concepts=tuple(concepts),
    )


def classify_history_search(query: HistoryQuery, matched_fact_count: int) -> str:
    """Geçmiş aramasının üç durumu. Kavram yoksa eşleşme yoktur."""
    if not query.active:
        return "inactive"
    if not query.resolved:
        return "UNRESOLVED"
    if matched_fact_count:
        return "MATCH"
    return "NO_MATCH"


# Tarih ve vizit kimliği bu metne girmez. İlgi, kod ve klinik ifadeden gelir.
_SUPPORT_ATTRS = ("examName", "departmentName", "requestingDepartment")
_SUPPORTING_FACT_LIMIT = 8


def history_support_terms(concepts: tuple[HistoryConcept, ...]) -> tuple[str, ...]:
    """Kavramın hastalık adları. Gün ve vizit bu listeye yazılmaz."""
    terms: list[str] = []
    for concept in concepts:
        for term in concept.support_terms:
            folded = fold(term)
            if len(folded) >= 3 and folded not in terms:
                terms.append(folded)
    return tuple(terms)


def fact_support_text(fact: object) -> str:
    """Tanıyı destekleyip desteklemediğine bakılacak klinik metin.

    `occurredFrom`, `visitDate` ve kanıt kimliği bu metne katılmaz.
    """
    parts: list[str] = [
        str(getattr(fact, "display_text", "") or ""),
        str(getattr(fact, "code", "") or ""),
        str(getattr(fact, "canonical_id", "") or ""),
        str(getattr(fact, "definition", "") or ""),
    ]
    narrative = getattr(fact, "narrative_sections", {}) or {}
    parts.extend(str(value) for value in narrative.values())
    attributes = getattr(fact, "clinical_attributes", {}) or {}
    for key in _SUPPORT_ATTRS:
        parts.append(str(attributes.get(key) or ""))
    return " ".join(parts)


def text_supports_history(
    text: str,
    concepts: tuple[HistoryConcept, ...],
    extra_terms: tuple[str, ...] = (),
) -> bool:
    """Metin, kavramın adını veya seçilen tanının kodunu taşıyor mu?"""
    folded = fold(text)
    terms = list(history_support_terms(concepts))
    for term in extra_terms:
        folded_term = fold(term)
        if len(folded_term) >= 3 and folded_term not in terms:
            terms.append(folded_term)
    return any(term in folded for term in terms)


def select_supporting_facts(
    candidates: list[object],
    concepts: tuple[HistoryConcept, ...],
    *,
    coded_facts: list[object],
    limit: int = _SUPPORTING_FACT_LIMIT,
) -> list[object]:
    """Kodlu tanıyı metin olarak destekleyen kayıtlar.

    Adaylar deponun zaman sırasıyla gelir. Aynı gün veya aynı vizitte olmak
    seçim ölçütü değildir; kodlu tanı yoksa destek kaydı da yoktur.
    """
    if not coded_facts or not concepts:
        return []
    coded_aliases: set[str] = set()
    extra_terms: list[str] = []
    for fact in coded_facts:
        alias = str(getattr(fact, "fact_alias", "") or "")
        if alias:
            coded_aliases.add(alias)
        code = str(getattr(fact, "code", "") or "")
        if code:
            extra_terms.append(code)
            compact = code.replace(".", "")
            if compact != code:
                extra_terms.append(compact)
        display = str(getattr(fact, "display_text", "") or "")
        if display:
            extra_terms.append(display)
    chosen: list[object] = []
    for fact in candidates:
        if str(getattr(fact, "fact_alias", "") or "") in coded_aliases:
            continue
        if text_supports_history(fact_support_text(fact), concepts, tuple(extra_terms)):
            chosen.append(fact)
            if len(chosen) >= limit:
                break
    return chosen


def diagnosis_status_label(type_value: str | None) -> str:
    """Kayıttaki tür etiketini aynen korur. Ön tanıyı kesin tanı yapmaz."""
    folded = (type_value or "").casefold().strip()
    if folded in {"preliminary", "ön tanı", "on tani"}:
        return "ön tanı"
    if folded in {"differential", "ayırıcı tanı", "ayirici tani"}:
        return "ayırıcı tanı"
    if folded in {"confirmed", "definitive", "final", "kesin", "kesin tanı"}:
        return "kesin tanı"
    return "kodlu tanı kaydı"


def compose_coded_history_answer(
    *,
    case_id: str,
    status: str,
    coded_facts: list[object],
) -> str:
    """Kodlu geçmiş satırlarından deterministik yanıt. Model tanının türünü değiştirmez."""
    if status == "UNRESOLVED":
        return (
            "Bu sorudaki kavram bir ICD-10 bölümüne bağlanamadı; "
            f"kodlu arama yapılmadı [CCO:{case_id}:HISTORY-UNRESOLVED]."
        )
    if status != "MATCH":
        return (
            "Bu aramada eşleşen aktif kodlu tanı bulunmamaktadır "
            f"[CCO:{case_id}:HISTORY-EMPTY]."
        )
    sentences: list[str] = []
    for fact in coded_facts:
        attributes = getattr(fact, "clinical_attributes", {}) or {}
        label = diagnosis_status_label(str(attributes.get("type") or ""))
        code = getattr(fact, "code", "") or ""
        display = getattr(fact, "display_text", "") or "kayıtlı tanı"
        occurred = str(getattr(fact, "occurred_from", "") or "")[:10]
        alias = getattr(fact, "fact_alias", "")
        sentences.append(
            f"Kayıtlı kod {code} {display}. Durum: {label}. Olay zamanı: {occurred}. "
            f"[CCO:{case_id}:{alias}]."
        )
    return " ".join(sentences)
