"""Kullanıcı sorusunun niyetini ve hedef CCO veri ailelerini belirleyen yönlendirici."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from medical_rag.rag.text import fold
from medical_rag.safety.emergency import EmergencyDecision, check_emergency
from medical_rag.twin.clinical_history import parse_history_query

_FAMILY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("sleep", re.compile(r"\buyku|uyudum|uyuyam|gece\s+uy|rem\b|derin\s+uyku|yatış")),
    ("cardio", re.compile(r"\bhrv\b|\bnabız|\bnabzım|\bkalp|çarpıntı|ritim|vo2max|bradikardi|taşikardi")),
    ("activity", re.compile(r"\badım|\bhareket|\byürüyüş|\baktivite")),
    ("hydration", re.compile(r"\bsu\s+tüket|\bsu\s+iç|\bhidrasyon|\bmililitre")),
    ("wellness", re.compile(r"\bstres\b|\bgergin")),
    ("oxygen", re.compile(r"\boksijen|\bspo2|\bsatürasyon")),
    ("recovery", re.compile(r"\bsolunum|\bsıcaklık|\bateş|\btoparlanma")),
    ("vitals", re.compile(r"\bkilo|\bağırlık|\bboy\b|\bbmi\b|\bvki\b|\bbel\s+çevre|\btansiyon|kan\s+basınc")),
    ("glucose", re.compile(r"\bglukoz|\bglikoz|kan\s+şeker|\bhba1c|\bşekerim")),
    (
        "lab",
        re.compile(
            r"\btahlil|\blaboratuvar|\bhemogram|\bhemoglobin|\bhematokrit|\bwbc|\bplt|\bmcv"
            r"|\bkreatinin|\begfr|\bkolesterol|\bldl|\bhdl|\btrigliseri|\bb12|d\s+vitamin"
            r"|\btsh|\bft3|\bft4|\balt\b|\bast\b"
        ),
    ),
    ("medication", re.compile(r"\bilaç|\bilacım|\breçete|\bkullandığım|\btakviye")),
    ("diagnosis", re.compile(r"\btanı|\bteşhis|\bhastalık|\bikd|\bicd|aile\s+öykü")),
    ("visit", re.compile(r"\bmuayene|\bbaşvuru|\bhastane|\bpoliklinik|\bvizit|\bameliyat|\bepikriz")),
    ("imaging", re.compile(r"\bgörüntüleme|\bradyoloji|\bmr\b|\bbt\b|\btomografi|\bröntgen|\bultrason")),
    ("pathology", re.compile(r"\bpatoloji|\bbiyopsi")),
    ("allergy", re.compile(r"\balerji")),
    ("data", re.compile(r"\byüzük|\bsensör|veri\s+durumu|eksik\s+veri|\bkapsam")),
)

_CANONICAL_HINTS: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = (
    (
        re.compile(r"son\s+ana\s+uyku|son\s+uyku"),
        ("sleep.duration.last-main-sleep", "sleep.score.last-main-sleep", "sleep.efficiency.last-main-sleep"),
    ),
    (
        re.compile(r"7\s*günlük\s+uyku|haftalık\s+uyku|uyku\s+ortalama"),
        ("sleep.duration.7d-average", "sleep.efficiency.7d-average"),
    ),
    (
        re.compile(r"hrv.{0,25}bazal|bazal.{0,25}hrv|kişisel\s+bazal"),
        ("cardio.hrv.personal-baseline", "cardio.hrv.day"),
    ),
    (
        re.compile(r"\bhrv\b"),
        ("cardio.hrv.day", "cardio.hrv.personal-baseline", "cardio.hrv.below-band-days-7d"),
    ),
    (
        re.compile(r"dinlenik\s+nabız|istirahat\s+nab"),
        ("cardio.resting-heart-rate.day", "cardio.resting-heart-rate.personal-baseline"),
    ),
)

_PERSONAL_INTENT_RE = re.compile(
    r"kayıtlarım|verilerim|ölçümlerim|sonuçlarım|benim|uykum|nabzım|tansiyonum"
    r"|ilaçlarım|tanılarım|tahlillerim|alerjim|özetim|durumum|görünmüyor|eksik"
    r"|kaç\s+dakika|ortalamam|son\s+\d+\s*gün"
)


@dataclass(frozen=True)
class RoutePlan:
    intent: str
    # "emergency" | "legacy_dictionary" | "patient_exact_query"
    # | "patient_symptom_twin" | "terminology_lookup" | "out_of_scope"
    case_id: str | None
    emergency: EmergencyDecision
    target_families: list[str] = field(default_factory=list)
    target_canonical_ids: list[str] = field(default_factory=list)
    linked_concepts: list[LinkedConcept] = field(default_factory=list)
    history_prefixes: tuple[str, ...] = ()
    history_concepts: tuple[tuple[str, str], ...] = ()


class IntentRouter:
    """Acil durum, sözlük ve kişisel Digital Twin sorgularını deterministik yönlendirir."""

    def __init__(self, linker: ConceptLinker | None = None) -> None:
        self._linker = linker

    def route(
        self,
        question: str,
        *,
        case_id: str | None = None,
        has_corpus_hits: bool = False,
    ) -> RoutePlan:
        emergency = check_emergency(question)
        if emergency.is_emergency:
            return RoutePlan(
                intent="emergency",
                case_id=case_id,
                emergency=emergency,
            )

        if not case_id:
            return RoutePlan(
                intent="legacy_dictionary",
                case_id=None,
                emergency=emergency,
            )

        folded = fold(question)
        matched_families: list[str] = []
        for family, pattern in _FAMILY_PATTERNS:
            if pattern.search(folded) and family not in matched_families:
                matched_families.append(family)

        canonical_ids: list[str] = []
        for pattern, cids in _CANONICAL_HINTS:
            if pattern.search(folded):
                for cid in cids:
                    if cid not in canonical_ids:
                        canonical_ids.append(cid)

        linked_concepts: list[LinkedConcept] = []
        if self._linker is not None:
            linked_concepts = self._linker.link_text(question, max_concepts=3)
            for concept in linked_concepts:
                for fam in concept.cco_families:
                    if fam not in matched_families:
                        matched_families.append(fam)

        is_personal_cue = bool(_PERSONAL_INTENT_RE.search(folded))
        history = parse_history_query(folded)

        # Tamamen alakasız soruları (ör. hava durumu, kuantum kapısı) erken ele
        if (
            not history.active
            and not matched_families
            and not linked_concepts
            and not is_personal_cue
            and not has_corpus_hits
        ):
            return RoutePlan(
                intent="out_of_scope",
                case_id=case_id,
                emergency=emergency,
            )

        # Genel kişisel özet istenmişse ("kayıtlarımda ne var?") temel aileleri seç
        if not matched_families and is_personal_cue:
            matched_families = [
                "sleep",
                "cardio",
                "vitals",
                "diagnosis",
                "medication",
                "lab",
            ]

        # allergy sanal ipucu için medication/diagnosis ailelerini de dahil et
        normalized_families = [f for f in matched_families if f != "allergy"]
        if "allergy" in matched_families:
            for extra in ("diagnosis", "medication"):
                if extra not in normalized_families:
                    normalized_families.append(extra)

        if history.active:
            intent = "clinical_history_search"
            for family in ("diagnosis", "visit", "imaging", "pathology"):
                if family not in normalized_families:
                    normalized_families.append(family)
        elif linked_concepts and (normalized_families or is_personal_cue):
            intent = "patient_symptom_twin"
        elif normalized_families or is_personal_cue:
            intent = "patient_exact_query"
        elif linked_concepts:
            intent = "terminology_lookup"
        else:
            intent = "patient_exact_query"

        return RoutePlan(
            intent=intent,
            case_id=case_id,
            emergency=emergency,
            target_families=normalized_families,
            target_canonical_ids=canonical_ids,
            linked_concepts=linked_concepts,
            history_prefixes=history.code_prefixes,
            history_concepts=tuple(
                (concept.concept_id, concept.label)
                for concept in history.concepts
                if concept.concept_id
            ),
        )
