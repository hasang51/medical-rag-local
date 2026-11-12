"""Modelden önce çalışan deterministik klinik acil durum (red-flag) denetleyicisi.

Kırmızı bayrak saptandığında LLM çağrılmaz (`eval_count = 0`). Giyilebilir cihaz
(yüzük/saat) veya geçmiş CCO kayıtlarının normal görünmesinin akut acil durumu
dışlayamayacağı açıkça belirtilerek doğrudan 112 Acil Çağrı Merkezi uyarısı döner.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from medical_rag.rag.text import fold

EMERGENCY_TEXT = (
    "ACİL DURUM UYARISI: Sorunuzda akut tıbbi değerlendirme gerektiren ciddi bir belirti "
    "(kırmızı bayrak) saptandı. Akıllı yüzük, saat veya geçmiş kişisel sağlık kayıtlarınızın "
    "normal görünmesi kalp krizi, inme veya yaşamı tehdit eden acil bir durumu dışlamaz. "
    "Lütfen beklemeden derhal 112 Acil Çağrı Merkezi'ni arayın veya en yakın acil servise başvurun."
)


@dataclass(frozen=True)
class EmergencyDecision:
    is_emergency: bool
    category: str | None = None
    matched_rule: str | None = None
    message: str = ""


_RED_FLAG_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "acute_chest_coronary",
        "göğüs ağrısı / baskı / yayılan ağrı",
        re.compile(
            r"göğsümde.{0,30}(?:ağr|baskı|sıkış|yanma)"
            r"|göğüs\s*(?:ağrısı|baskısı|sıkışması)"
            r"|sol\s+kol(?:uma|a).{0,25}(?:yayıl|uyuş|ağr)"
            r"|kalp\s+krizi\s+geçir"
        ),
    ),
    (
        "acute_severe_dyspnea",
        "akut nefes alamama / boğulma / siyanoz",
        re.compile(
            r"nefes\s+alamıyor"
            r"|boğuluyor\s+gibiyim"
            r"|dudaklarım\s+morar"
            r"|şiddetli\s+nefes\s+darlığ"
            r"|ani\s+nefes\s+darlığ"
        ),
    ),
    (
        "acute_stroke_neuro",
        "inme / nörolojik kayıp / yıldırım baş ağrısı",
        re.compile(
            r"yüzümde\s+(?:kayma|uyuşma|felç)"
            r"|konuşmam\s+bozul|konuşamıyorum|peltek\s+konuş"
            r"|kolum\s+tutmuyor|bacağım\s+tutmuyor"
            r"|tek\s+taraflı\s+(?:uyuşma|güçsüzlük|felç)"
            r"|\binme\s+geçir"
            r"|(?:hayatımın\s+en|ani\s+çok)\s+şiddetli\s+baş\s*ağr"
            r"|ani\s+görme\s+kayb"
        ),
    ),
    (
        "syncope_seizure",
        "bilinç kaybı / bayılma / nöbet",
        re.compile(
            r"\bbayıldım\b"
            r"|bilincini\s+kaybet|bilinç\s+kaybı"
            r"|nöbet\s+geçiriyorum|havale\s+geçir"
        ),
    ),
    (
        "anaphylaxis_hemorrhage",
        "anafilaksi / durdurulamayan kanama",
        re.compile(
            r"dilim\s+şiş|boğazım\s+şiş|\banafilaksi"
            r"|durdurulamayan\s+kanama|kan\s+kusuyor|kan\s+tükürüyor"
        ),
    ),
    (
        "self_harm_crisis",
        "kendine zarar verme / intihar krizi",
        re.compile(
            r"\bintihar\b"
            r"|kendime\s+zarar\s+ver"
            r"|yaşamıma\s+son"
            r"|ölmek\s+istiyorum"
        ),
    ),
)


def check_emergency(question: str) -> EmergencyDecision:
    """Kullanıcı sorusunu model çağrılmadan önce kırmızı bayrak kurallarıyla denetler."""
    folded = fold(question)
    for category, label, pattern in _RED_FLAG_RULES:
        if pattern.search(folded):
            return EmergencyDecision(
                is_emergency=True,
                category=category,
                matched_rule=label,
                message=EMERGENCY_TEXT,
            )
    return EmergencyDecision(is_emergency=False)
