"""CCO zaman pencereleri, referans zamanı, supersession ve eksik veri çözümleyicisi.

Temel kurallar:
1. Olay zamanı `occurredFrom..occurredTo`, kanıt zamanı `evidence[].occurredAt`,
   değerlendirici kayıt zamanı ise `recordedAt` alanıdır; birbirlerinin yerine kullanılmaz.
2. Bağıl zaman ifadeleri ("son 7 gün", "son 30 gün", "dün") duvar saatine göre değil,
   vakanın kendi `evaluated_at` / `cco_as_of` referans zamanına göre çözülür.
3. Türetilmiş pencere tanımları (`7d-average`, `30d-average`, `personal-baseline`, `trend`)
   günlük veya tekil ölçümlerle tekrar ortalanmaz.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from medical_rag.rag.text import fold
from medical_rag.twin.cco_adapter import AdaptedFact, AdaptedNarrativeSection
from medical_rag.twin.fact_repository import (
    MissingDataGroupSummary,
    NumericSeriesSummary,
    PatientFactRepository,
    PatientSummary,
)

_DERIVED_WINDOW_MARKERS = (
    "average",
    "mean",
    "baseline",
    "trend",
    "streak",
    "variability",
    "jetlag",
    "attainment",
    "band-low",
    "band-high",
    "below-band",
    "above-band",
    "high-nights",
    "low-nights",
    "nights-2d",
    "nights-3d",
    "recent-window",
    "elevated-count",
    "high-count",
    "low-count",
    "hours-since",
)

_DAYS_RE = re.compile(r"son\s+(\d{1,3})\s*g[uü]n")
_WEEKS_RE = re.compile(r"son\s+(\d{1,2})\s*hafta")
_MONTHS_RE = re.compile(r"son\s+(\d{1,2})\s*ay")


def parse_iso_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def is_derived_window_metric(canonical_id: str) -> bool:
    """Tanımın çok günlü/pencere türevi olup olmadığını belirler."""
    return any(marker in canonical_id for marker in _DERIVED_WINDOW_MARKERS)


@dataclass(frozen=True)
class TemporalWindow:
    label: str
    reference_at: str
    since_iso: str | None
    until_iso: str | None
    days: int | None


@dataclass(frozen=True)
class ResolvedFactView:
    fact: AdaptedFact
    glossary_label: str
    glossary_description: str
    is_point_event: bool
    is_derived_window: bool
    is_expired_at_reference: bool


@dataclass(frozen=True)
class PatientTemporalSnapshot:
    patient: PatientSummary
    window: TemporalWindow
    latest_facts: list[ResolvedFactView]
    numeric_summaries: list[NumericSeriesSummary]
    missing_groups: list[MissingDataGroupSummary]
    narrative_sections: list[AdaptedNarrativeSection]


class TemporalResolver:
    """Hasta sorusundaki zaman kapsamını ve güncel aktif CCO görünümünü çözümler."""

    def __init__(self, repo: PatientFactRepository) -> None:
        self._repo = repo

    def resolve_window(self, patient: PatientSummary, question: str) -> TemporalWindow:
        ref_str = patient.evaluated_at or patient.cco_as_of or patient.exported_at
        ref_dt = parse_iso_timestamp(ref_str)
        folded = fold(question)

        days: int | None = None
        label = "tüm aktif kayıtlar (en güncel öncelikli)"

        m_days = _DAYS_RE.search(folded)
        m_weeks = _WEEKS_RE.search(folded)
        m_months = _MONTHS_RE.search(folded)
        if m_days:
            days = int(m_days.group(1))
            label = f"referans tarihten önceki son {days} gün"
        elif m_weeks:
            days = int(m_weeks.group(1)) * 7
            label = f"referans tarihten önceki son {days} gün"
        elif m_months:
            days = int(m_months.group(1)) * 30
            label = f"referans tarihten önceki son {days} gün"
        elif "bu hafta" in folded or "haftalık" in folded or "7 günlük" in folded:
            days = 7
            label = "referans tarihten önceki son 7 gün"
        elif "bu ay" in folded or "aylık" in folded or "30 günlük" in folded:
            days = 30
            label = "referans tarihten önceki son 30 gün"
        elif "dün" in folded or "son gece" in folded or "bu gece" in folded:
            days = 3
            label = "referans tarihe en yakın son 3 gün"

        if days is not None and ref_dt is not None:
            since_dt = ref_dt - timedelta(days=days)
            return TemporalWindow(
                label=label,
                reference_at=ref_str,
                since_iso=since_dt.isoformat(),
                until_iso=ref_dt.isoformat(),
                days=days,
            )

        return TemporalWindow(
            label=label,
            reference_at=ref_str,
            since_iso=None,
            until_iso=ref_dt.isoformat() if ref_dt is not None else None,
            days=None,
        )

    def build_snapshot(
        self,
        case_id: str,
        question: str,
        *,
        families: list[str] | None = None,
        canonical_ids: list[str] | None = None,
        priority_canonical_ids: list[str] | None = None,
        max_facts_per_metric: int = 2,
        max_total_facts: int = 18,
    ) -> PatientTemporalSnapshot | None:
        patient = self._repo.get_patient(case_id)
        if patient is None:
            return None

        window = self.resolve_window(patient, question)
        if not patient.has_structured_data:
            narratives = self._repo.get_narrative_sections(case_id)
            return PatientTemporalSnapshot(
                patient=patient,
                window=window,
                latest_facts=[],
                numeric_summaries=[],
                missing_groups=[],
                narrative_sections=narratives,
            )

        glossary = self._repo.get_glossary_map(case_id)
        ref_dt = parse_iso_timestamp(window.reference_at)

        # Önce pencere içi aktif başarı kayıtlarını ara; pencere boş dönerse
        # en güncel aktif kayıtlara geri düş (pencere dışı notu korunarak).
        candidates = self._repo.query_facts(
            case_id,
            families=families,
            canonical_ids=canonical_ids,
            evaluation_status="success",
            active_only=True,
            occurred_since=window.since_iso,
            include_details=True,
        )
        if not candidates and window.since_iso is not None:
            candidates = self._repo.query_facts(
                case_id,
                families=families,
                canonical_ids=canonical_ids,
                evaluation_status="success",
                active_only=True,
                include_details=True,
            )

        # Her canonical_id (veya kodlu tanı/ilaç için evaluation_key) başına en güncel satırları seç
        per_key_counts: dict[str, int] = {}
        selected_views: list[ResolvedFactView] = []
        seen_numeric_canonicals: list[str] = []

        for fact in candidates:
            group_key = (
                f"{fact.canonical_id}:{fact.code}"
                if fact.value_type == "coded" and fact.code
                else fact.canonical_id
            )
            current = per_key_counts.get(group_key, 0)
            if current >= max_facts_per_metric:
                continue
            per_key_counts[group_key] = current + 1

            g_entry = glossary.get(fact.definition) or glossary.get(fact.canonical_id)
            valid_until_dt = (
                parse_iso_timestamp(fact.valid_until) if fact.valid_until else None
            )
            is_expired = bool(
                ref_dt is not None
                and valid_until_dt is not None
                and valid_until_dt < ref_dt
            )
            selected_views.append(
                ResolvedFactView(
                    fact=fact,
                    glossary_label=g_entry.label if g_entry else fact.canonical_id,
                    glossary_description=g_entry.description if g_entry else "",
                    is_point_event=(fact.occurred_from == fact.occurred_to),
                    is_derived_window=is_derived_window_metric(fact.canonical_id),
                    is_expired_at_reference=is_expired,
                )
            )
            if (
                fact.amount is not None
                and not is_derived_window_metric(fact.canonical_id)
                and fact.canonical_id not in seen_numeric_canonicals
            ):
                seen_numeric_canonicals.append(fact.canonical_id)
            if len(selected_views) >= max_total_facts:
                break

        # Yalnızca ham/günlük/seri metrikler için Python/SQL istatistiği üret;
        # pencere ortalamalarını tekrar ortalamaya sokma!
        numeric_summaries: list[NumericSeriesSummary] = []
        for canon_id in seen_numeric_canonicals[:8]:
            stats = self._repo.compute_numeric_stats(
                case_id,
                canon_id,
                occurred_since=window.since_iso,
            )
            if stats is None and window.since_iso is not None:
                stats = self._repo.compute_numeric_stats(case_id, canon_id)
            if stats is not None:
                numeric_summaries.append(stats)

        all_missing_groups = self._repo.summarize_missing_data(
            case_id,
            families=families,
        )
        priority_set = set(priority_canonical_ids or [])
        all_missing_groups.sort(
            key=lambda g: (0 if g.canonical_id in priority_set else 1, g.canonical_id, g.definition_version)
        )
        missing_groups = all_missing_groups[:10]

        # Hasta beyanı bölümleri + seçili ailelerle eşleşen anlatısal bölümler
        self_reported = self._repo.get_narrative_sections(
            case_id, self_reported_only=True
        )
        family_narratives: list[AdaptedNarrativeSection] = []
        if families:
            family_narratives = self._repo.get_narrative_sections(
                case_id,
                self_reported_only=False,
                family_hints=families,
            )
        merged_narratives: list[AdaptedNarrativeSection] = []
        seen_slugs: set[str] = set()
        for sec in [*self_reported, *family_narratives]:
            if sec.section_slug not in seen_slugs:
                seen_slugs.add(sec.section_slug)
                merged_narratives.append(sec)

        return PatientTemporalSnapshot(
            patient=patient,
            window=window,
            latest_facts=selected_views,
            numeric_summaries=numeric_summaries,
            missing_groups=missing_groups,
            narrative_sections=merged_narratives[:6],
        )
