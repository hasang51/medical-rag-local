"""Hasta kayıtları (CCO), SNOMED terminolojisi ve genel bilgiyi ayıran kanıt üretici.

Üç katman birbirine karıştırılmaz:
- Katman 1 (`patient_cco`): `[CCO:<case_id>:...]` — SQLite/Python kesin hasta kayıtları,
  sayısal hesaplamalar, eksik veri (`data-required`) nedenleri ve hasta beyanı bölümleri.
- Katman 2 (`snomed_terminology`): `[SNOMED:<concept_id>]` — aktif SNOMED CT IPS kavramları
  ve korunmuş ilişki türleri (`Is a`, `Finding site` vb., tanı olasılığı olmadan).
- Katman 3 (`general_knowledge`): `[GENEL:<chunk_id>]` — genel eğitim sözlüğü parçaları.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from medical_rag.rag.retriever import ScoredChunk
from medical_rag.terminology.concept_linker import LinkedConcept
from medical_rag.twin.temporal_resolver import PatientTemporalSnapshot, ResolvedFactView


def _slugify(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()[:36] or "item"


def _fmt_number(value: float | None) -> str:
    if value is None:
        return "null"
    if float(value).is_integer():
        return str(int(value))
    return str(value)


@dataclass(frozen=True)
class EvidenceItem:
    citation_id: str
    layer: str  # "patient_cco" | "snomed_terminology" | "general_knowledge"
    title: str
    summary: str
    occurred_window: str = ""
    recorded_at: str = ""


@dataclass(frozen=True)
class LayeredEvidenceBundle:
    case_id: str
    patient_cco: list[EvidenceItem] = field(default_factory=list)
    snomed_terminology: list[EvidenceItem] = field(default_factory=list)
    general_knowledge: list[EvidenceItem] = field(default_factory=list)

    @property
    def allowed_citation_ids(self) -> list[str]:
        return [
            *(item.citation_id for item in self.patient_cco),
            *(item.citation_id for item in self.snomed_terminology),
            *(item.citation_id for item in self.general_knowledge),
        ]

    def render_prompt_context(self, *, max_chars: int = 7500) -> str:
        snomed_budget = min(1600, max_chars // 4) if self.snomed_terminology else 0
        general_budget = min(1100, max_chars // 6) if self.general_knowledge else 0
        cco_budget = max(1500, max_chars - snomed_budget - general_budget - 120)

        def _render_layer(header: str, items: list[EvidenceItem], budget: int) -> str:
            lines = [header]
            used = len(header)
            for item in items:
                block = f"[{item.citation_id}] {item.title}\n{item.summary}"
                if used + len(block) + 2 > budget and len(lines) > 1:
                    break
                if len(lines) == 1 and used + len(block) + 2 > budget:
                    allowed = max(120, budget - used - 6)
                    block = block[:allowed] + "..."
                lines.append(block)
                used += len(block) + 2
            return "\n\n".join(lines)

        sections: list[str] = []
        if self.patient_cco:
            sections.append(
                _render_layer(
                    "=== KATMAN 1: HASTA KİŞİSEL CCO KAYITLARI VE KESİN PYTHON/SQL HESAPLARI ===",
                    self.patient_cco,
                    cco_budget,
                )
            )
        if self.snomed_terminology:
            sections.append(
                _render_layer(
                    "=== KATMAN 2: SNOMED CT IPS TERMİNOLOJİ BİLGİSİ (YAPISAL TANIM — TANI OLASILIĞI DEĞİLDİR) ===",
                    self.snomed_terminology,
                    snomed_budget,
                )
            )
        if self.general_knowledge:
            sections.append(
                _render_layer(
                    "=== KATMAN 3: GENEL KLİNİK EĞİTİM SÖZLÜĞÜ (KİŞİSEL HASTA KAYDI DEĞİLDİR) ===",
                    self.general_knowledge,
                    general_budget,
                )
            )

        rendered = "\n\n".join(sections)
        if len(rendered) <= max_chars:
            return rendered
        return rendered[: max_chars - 3] + "..."


def _format_fact_view(view: ResolvedFactView) -> EvidenceItem:
    fact = view.fact
    cid = f"CCO:{fact.case_id}:{fact.fact_alias}"
    window_text = (
        fact.occurred_from
        if view.is_point_event
        else f"{fact.occurred_from} .. {fact.occurred_to}"
    )

    if fact.amount is not None:
        val_str = f"{_fmt_number(fact.amount)} {fact.unit or ''}".strip()
    elif fact.value_type == "coded":
        val_str = f"{fact.display_text or ''} ({fact.code_system}:{fact.code})".strip()
    elif fact.value_type == "narrative" and fact.narrative_sections:
        sec_parts = [
            f"{k}: {v[:180]}" for k, v in list(fact.narrative_sections.items())[:3]
        ]
        val_str = " | ".join(sec_parts)
    else:
        val_str = "null (hesaplanamadı)"

    notes: list[str] = [
        f"Değer: {val_str}",
        f"Kapsam Anahtarı: {fact.evaluation_key}",
        f"Olay Zamanı: {window_text} | Kayıt Zamanı (recordedAt): {fact.recorded_at}",
    ]
    if view.glossary_description:
        notes.append(f"Tanım Notu: {view.glossary_description}")
    if fact.clinical_attributes:
        attr_str = ", ".join(f"{k}={v}" for k, v in sorted(fact.clinical_attributes.items()))
        notes.append(f"Klinik Öznitelikler: {attr_str}")
    if fact.evidence:
        src_types = sorted({ev.source_type for ev in fact.evidence if ev.source_type})
        notes.append(
            f"Kanıt Kaynağı: {', '.join(src_types)} ({len(fact.evidence)} referans)"
        )
    if fact.code_system == "tr-drug-barcode":
        notes.append(
            "Uyarı: Bu satır reçete kaydıdır; ilacın bugün fiilen içildiğini tek başına kanıtlamaz."
        )
    if view.is_derived_window:
        notes.append("Not: Bu metrik çok günlü/pencere türevidir; tekil saatlik ölçüm değildir.")
    if view.is_expired_at_reference:
        notes.append(f"Not: validUntil ({fact.valid_until}) referans tarihten öncedir.")

    return EvidenceItem(
        citation_id=cid,
        layer="patient_cco",
        title=f"{view.glossary_label} ({fact.canonical_id})",
        summary="\n".join(notes),
        occurred_window=window_text,
        recorded_at=fact.recorded_at,
    )


class EvidenceBuilder:
    """Sorgu planı, hasta zaman görünümü, SNOMED kavramları ve genel BM25 parçalarını birleştirir."""

    def build(
        self,
        *,
        case_id: str,
        snapshot: PatientTemporalSnapshot | None,
        targeted_facts: list[ResolvedFactView] | None = None,
        linked_concepts: list[LinkedConcept] | None = None,
        general_chunks: list[ScoredChunk] | None = None,
        history_mode: bool = False,
        history_facts: list[ResolvedFactView] | None = None,
        history_prefixes: tuple[str, ...] = (),
    ) -> LayeredEvidenceBundle:
        cco_items: list[EvidenceItem] = []
        seen_citations: set[str] = set()

        def _add_cco(item: EvidenceItem) -> None:
            if item.citation_id not in seen_citations:
                seen_citations.add(item.citation_id)
                cco_items.append(item)

        if history_mode:
            chapter = ", ".join(history_prefixes) if history_prefixes else "tüm kodlu tanılar"
            _add_cco(
                EvidenceItem(
                    citation_id=f"CCO:{case_id}:HISTORY-SCOPE",
                    layer="patient_cco",
                    title="Kodlu geçmiş araması",
                    summary=(
                        f"Arama bölümü: {chapter}. "
                        "Sonuç kodlu tanı satırlarıdır. Kesin tanı sayısı veya genel sözlük "
                        "bu aramanın yokluk kanıtı değildir."
                    ),
                )
            )
            if not history_facts:
                _add_cco(
                    EvidenceItem(
                        citation_id=f"CCO:{case_id}:HISTORY-EMPTY",
                        layer="patient_cco",
                        title="Eşleşen kodlu geçmiş yok",
                        summary=(
                            "Bu aramada eşleşen aktif kodlu tanı bulunmadı. "
                            "Bu yokluk yalnız bu arama içindir."
                        ),
                    )
                )
            else:
                for view in history_facts:
                    _add_cco(_format_fact_view(view))
        elif snapshot is None:
            _add_cco(
                EvidenceItem(
                    citation_id=f"CCO:{case_id}:NOT-FOUND",
                    layer="patient_cco",
                    title="Hasta Profili Bulunamadı",
                    summary=f"{case_id} için yerel veritabanında kayıt bulunamadı.",
                )
            )
        elif not snapshot.patient.has_structured_data:
            _add_cco(
                EvidenceItem(
                    citation_id=f"CCO:{case_id}:EMPTY",
                    layer="patient_cco",
                    title=f"{case_id} Yapısal CCO Kayıt Durumu",
                    summary=(
                        f"Referans tarihi ({snapshot.window.reference_at}) itibarıyla bu hastanın "
                        "CCO dışa aktarımında 0 yapısal fact ve 0 missingData satırı bulunmaktadır. "
                        "Olmayan ölçüm, tanı veya ilaç verisi uydurulmamalıdır."
                    ),
                )
            )
            for sec in snapshot.narrative_sections:
                _add_cco(
                    EvidenceItem(
                        citation_id=f"CCO:{case_id}:BEYAN-{_slugify(sec.section_slug)}",
                        layer="patient_cco",
                        title=f"CCO Metin Bölümü: {sec.heading}",
                        summary=sec.content[:400],
                    )
                )
        else:
            # 1. Hedefli metrik satırları (ör. doğrudan sorulan canonical_id)
            for view in targeted_facts or []:
                _add_cco(_format_fact_view(view))

            # 2. Kesin Python/SQL seri hesaplamaları
            for stat in snapshot.numeric_summaries[:6]:
                unit_txt = f" {stat.unit}" if stat.unit else ""
                _add_cco(
                    EvidenceItem(
                        citation_id=f"CCO:{case_id}:CALC-{_slugify(stat.canonical_id)}",
                        layer="patient_cco",
                        title=f"Kesin Python/SQL Seri Hesabı ({stat.canonical_id})",
                        summary=(
                            f"Gözlem Sayısı: {stat.sample_count} | "
                            f"Son Değer: {_fmt_number(stat.latest_amount)}{unit_txt} "
                            f"(Kaynak: {stat.latest_fact_alias}, Olay: {stat.latest_occurred_from} .. {stat.latest_occurred_to}) | "
                            f"Ortalama: {_fmt_number(stat.avg_amount)}{unit_txt} | "
                            f"Min: {_fmt_number(stat.min_amount)}{unit_txt} | "
                            f"Maks: {_fmt_number(stat.max_amount)}{unit_txt}"
                        ),
                        occurred_window=f"{stat.earliest_occurred_from} .. {stat.latest_occurred_to}",
                        recorded_at=stat.latest_recorded_at,
                    )
                )

            # 3. Güncel seçili aktif fact satırları
            for view in snapshot.latest_facts[:12]:
                _add_cco(_format_fact_view(view))

            # 4. Eksik / hesaplanamayan (`data-required`) sonuç grupları
            for grp in snapshot.missing_groups[:6]:
                reasons_str = ", ".join(grp.missing_reasons) if grp.missing_reasons else "belirtilmemiş"
                aliases_str = ", ".join(grp.sample_fact_aliases)
                _add_cco(
                    EvidenceItem(
                        citation_id=f"CCO:{case_id}:MISSING-{_slugify(grp.canonical_id)}",
                        layer="patient_cco",
                        title=f"Hesaplanamayan / Eksik Veri ({grp.canonical_id})",
                        summary=(
                            f"Durum: data-required (value=null; bu sonuç sıfır veya normal DEĞİLDİR) | "
                            f"Eksik Satır Sayısı: {grp.row_count} (Örnekler: {aliases_str}) | "
                            f"Gereksinim / Eksiklik Nedenleri: {reasons_str} | "
                            f"Zaman Kapsamı: {grp.earliest_occurred_from} .. {grp.latest_occurred_to}"
                        ),
                        occurred_window=f"{grp.earliest_occurred_from} .. {grp.latest_occurred_to}",
                    )
                )

            # 5. Hasta beyanı ve CCO anlatısal bölümleri
            for sec in snapshot.narrative_sections[:4]:
                tag = "Hasta Beyanı" if sec.is_self_reported else "CCO Özet Notu"
                _add_cco(
                    EvidenceItem(
                        citation_id=f"CCO:{case_id}:BEYAN-{_slugify(sec.section_slug)}",
                        layer="patient_cco",
                        title=f"{tag}: {sec.heading}",
                        summary=sec.content[:450],
                    )
                )

            if not cco_items:
                _add_cco(
                    EvidenceItem(
                        citation_id=f"CCO:{case_id}:NO-MATCH",
                        layer="patient_cco",
                        title="İlgili CCO Ailesinde Kayıt Durumu",
                        summary=(
                            f"{case_id} profilinde sorgulanan klinik aile için kayıtlı aktif "
                            "değer bulunmamaktadır."
                        ),
                    )
                )

        snomed_items: list[EvidenceItem] = []
        for concept in linked_concepts or []:
            outgoing = [
                f"{rel.type_label} ({rel.type_id}) -> {rel.target_preferred_term} [{rel.target_concept_id}]"
                for rel in concept.relationships
                if rel.direction == "outgoing"
            ]
            subtypes = [
                f"{rel.target_preferred_term} [{rel.target_concept_id}]"
                for rel in concept.relationships
                if rel.direction == "incoming_subtype"
            ]
            lines = [
                f"FSN: {concept.fsn} | Tercih Edilen Terim: {concept.preferred_term} | Eşleşen İfade: {concept.matched_phrase}",
                f"IPS Refset Üyesi: {'Evet' if concept.in_ips_refset else 'Hayır'} | Eşanlamlılar: {', '.join(concept.synonyms[:5])}",
            ]
            if outgoing:
                lines.append(f"Yapısal İlişkiler: {'; '.join(outgoing[:6])}")
            if subtypes:
                lines.append(f"Ontolojik Alt Kavram Örnekleri: {', '.join(subtypes[:5])}")
            lines.append(f"Sınır Notu: {concept.ontological_notice}")
            snomed_items.append(
                EvidenceItem(
                    citation_id=f"SNOMED:{concept.concept_id}",
                    layer="snomed_terminology",
                    title=f"SNOMED CT {concept.preferred_term} ({concept.concept_id})",
                    summary="\n".join(lines),
                )
            )

        general_items: list[EvidenceItem] = []
        for chunk in general_chunks or []:
            general_items.append(
                EvidenceItem(
                    citation_id=f"GENEL:{chunk.id}",
                    layer="general_knowledge",
                    title=f"Eğitim Sözlüğü ({chunk.source})",
                    summary=chunk.text,
                )
            )

        return LayeredEvidenceBundle(
            case_id=case_id,
            patient_cco=cco_items,
            snomed_terminology=snomed_items,
            general_knowledge=general_items,
        )
