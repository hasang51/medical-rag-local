"""Geçmiş hastalık araması.

En yeni giyilebilir kayıtların tavanı eski kodlu tanıları düşürür. Bu operatör
soruyu bir organ veya sistem bölümüne bağlar ve o bölümdeki kodlu tanıları
olay zamanından bağımsız getirir. Vaka adına veya tek bir hastalığa kilitlenmez.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

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


# Daha özel kavram, aynı kökü taşıyan genel kavramdan önce yazılır.
# Tiroid: E00–E07. Kalp: I01 ve I05–I09, I1–I5'in dışında kalan romatizmal bloktur.
_CHAPTERS: tuple[tuple[re.Pattern[str], HistoryConcept], ...] = (
    (
        re.compile(
            r"\bmide|\bgastr|reflü|reflu|ülser|ulser|özofaj|ozofaj|"
            r"\bsindirim|karın|karnım|bağırsak|bagirsak|bulantı|bulanti"
        ),
        HistoryConcept("", "sindirim sistemi", ("K2", "K3")),
    ),
    (
        re.compile(r"\bkalp|\bkardiy"),
        HistoryConcept(
            "56265001",
            "Heart disease",
            ("I01", "I05", "I06", "I07", "I08", "I09", "I1", "I2", "I3", "I4", "I5"),
        ),
    ),
    (
        re.compile(r"hipertans"),
        HistoryConcept("38341003", "Hypertensive disorder", ("I1",)),
    ),
    (
        re.compile(r"aritmi"),
        HistoryConcept("698247007", "Cardiac arrhythmia", ("I4",)),
    ),
    (
        re.compile(r"hipotiroid"),
        HistoryConcept("40930008", "Hypothyroidism", ("E0",)),
    ),
    (
        re.compile(r"hipertiroid"),
        HistoryConcept("34486009", "Hyperthyroidism", ("E05",)),
    ),
    (
        re.compile(r"tiroit|(?<!hipo)(?<!hiper)tiroid"),
        HistoryConcept("14304000", "Disorder of thyroid gland", ("E0",)),
    ),
    (
        re.compile(r"diyabet|şeker hastal|seker hastal"),
        HistoryConcept("73211009", "Diabetes mellitus", ("E1",)),
    ),
    (
        re.compile(r"\bastım|\bastim|\bkoah|bronşit|bronsit"),
        HistoryConcept("", "solunum", ("J4", "J45")),
    ),
    (
        re.compile(r"böbrek|bobrek|idrar yolu"),
        HistoryConcept("", "üriner", ("N1", "N2", "N3")),
    ),
    (
        re.compile(r"\banemi|kansız|kansiz"),
        HistoryConcept("", "anemi", ("D5", "D6")),
    ),
    (
        re.compile(r"depres|anksiye|panik atak"),
        HistoryConcept("", "duygudurum", ("F3", "F4")),
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
    matched_patterns: list[str] = []
    concepts: list[HistoryConcept] = []
    for pattern, concept in _CHAPTERS:
        if pattern.search(folded_question):
            matched_patterns.append(pattern.pattern)
            concepts.append(concept)
            for prefix in concept.code_prefixes:
                if prefix not in prefixes:
                    prefixes.append(prefix)
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
                        "hypothesisId": "A",
                        "location": "clinical_history.py:parse_history_query",
                        "message": "history chapter resolution",
                        "data": {
                            "folded": folded_question,
                            "active": True,
                            "matchedPatterns": matched_patterns,
                            "codePrefixes": prefixes,
                            "tiroitInText": "tiroit" in folded_question,
                            "tiroidInText": "tiroid" in folded_question,
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
