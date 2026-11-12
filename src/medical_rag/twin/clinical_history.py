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

# ICD-10 bölümü. Organ veya sistem adı eşlenir; hasta cümlesi üretilmez.
_CHAPTERS: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = (
    (
        re.compile(
            r"\bmide|\bgastr|reflü|reflu|ülser|ulser|özofaj|ozofaj|"
            r"\bsindirim|karın|karnım|bağırsak|bagirsak|bulantı|bulanti"
        ),
        ("K2", "K3"),
    ),
    (re.compile(r"\bkalp|\bkardiy|hipertans|aritmi"), ("I1", "I2", "I3", "I4", "I5")),
    (re.compile(r"tiroid|hipotiroid|hipertiroid"), ("E0",)),
    (re.compile(r"diyabet|şeker hastal|seker hastal"), ("E1",)),
    (re.compile(r"\bastım|\bastim|\bkoah|bronşit|bronsit"), ("J4", "J45")),
    (re.compile(r"böbrek|bobrek|idrar yolu"), ("N1", "N2", "N3")),
    (re.compile(r"\banemi|kansız|kansiz"), ("D5", "D6")),
    (re.compile(r"depres|anksiye|panik atak"), ("F3", "F4")),
)


@dataclass(frozen=True)
class HistoryQuery:
    active: bool
    code_prefixes: tuple[str, ...] = ()


def parse_history_query(folded_question: str) -> HistoryQuery:
    """Katlanmış soru geçmiş hastalık araması mı, hangi kod bölümünde?"""
    if not _HISTORY_CUES.search(folded_question):
        return HistoryQuery(active=False)
    prefixes: list[str] = []
    for pattern, chapter in _CHAPTERS:
        if pattern.search(folded_question):
            for prefix in chapter:
                if prefix not in prefixes:
                    prefixes.append(prefix)
    return HistoryQuery(active=True, code_prefixes=tuple(prefixes))
