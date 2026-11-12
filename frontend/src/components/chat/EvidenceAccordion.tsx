import { Check, ChevronDown, Database, FileSearch, GitBranch, Info } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type { EvidenceLayerItem, EvidenceLayers } from "@/types/api";

interface EvidenceAccordionProps {
  citations: string[];
  retrievedChunkIds: string[];
  evidenceLayers?: EvidenceLayers;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  highlightedChunkId?: string | null;
}

export function EvidenceAccordion({
  citations,
  retrievedChunkIds,
  evidenceLayers,
  open,
  onOpenChange,
  highlightedChunkId,
}: EvidenceAccordionProps) {
  const hasLayeredEvidence = Boolean(
    evidenceLayers &&
      (evidenceLayers.patient_cco.length > 0 ||
        evidenceLayers.snomed_terminology.length > 0 ||
        evidenceLayers.general_knowledge.length > 0)
  );

  if (!hasLayeredEvidence && citations.length === 0 && retrievedChunkIds.length === 0) {
    return null;
  }

  const citedSet = new Set(citations);
  const allChunkIds = Array.from(new Set([...retrievedChunkIds, ...citations]));

  const renderLayerGroup = (
    title: string,
    subtitle: string,
    items: EvidenceLayerItem[],
    badgeTone: "default" | "secondary" | "outline"
  ) => {
    if (items.length === 0) {
      return null;
    }
    return (
      <div className="space-y-1.5">
        <div className="flex flex-wrap items-center justify-between gap-2 px-1">
          <span className="text-xs font-semibold text-slate-800">{title}</span>
          <span className="text-[11px] text-slate-500">{subtitle}</span>
        </div>
        {items.map((item) => {
          const isCited = citedSet.has(item.citation_id);
          const isHighlighted = highlightedChunkId === item.citation_id;
          return (
            <div
              key={item.citation_id}
              className={`flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2 text-xs transition-colors ${
                isHighlighted
                  ? "border-teal-500 bg-teal-50/80 ring-1 ring-teal-500/30"
                  : isCited
                    ? "border-teal-200/90 bg-white"
                    : "border-slate-200/80 bg-white/60 text-slate-600"
              }`}
            >
              <div className="flex flex-col gap-0.5">
                <code className="font-mono text-xs font-semibold text-slate-900">
                  {item.citation_id}
                </code>
                <span className="text-[11px] text-slate-600">{item.title}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Badge variant={badgeTone} className="text-[11px] py-0">
                  {item.layer}
                </Badge>
                {isCited ? (
                  <Badge variant="success" className="text-[11px] py-0">
                    <Check className="h-3 w-3" />
                    Yanıtta Alıntılandı
                  </Badge>
                ) : (
                  <Badge variant="secondary" className="text-[11px] py-0">
                    Getirildi
                  </Badge>
                )}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <Collapsible
      open={open}
      onOpenChange={onOpenChange}
      className="rounded-xl border border-slate-200/90 bg-slate-50/70"
    >
      <CollapsibleTrigger className="flex w-full items-center justify-between gap-3 px-3.5 py-2.5 text-left text-xs font-medium text-slate-700 transition-colors hover:bg-slate-100/80 rounded-xl cursor-pointer">
        <div className="flex flex-wrap items-center gap-2">
          {hasLayeredEvidence ? (
            <Database className="h-4 w-4 text-teal-700" />
          ) : (
            <FileSearch className="h-4 w-4 text-teal-700" />
          )}
          <span className="font-semibold text-slate-800">
            {hasLayeredEvidence
              ? "3 Katmanlı Digital Twin Kanıt İzleri (CCO • SNOMED • Genel)"
              : "RAG Kanıt ve Getirilen Parça Kimlikleri"}
          </span>
          <Badge variant="default" className="px-2 py-0 text-[11px]">
            {citations.length} doğrulanmış alıntı
          </Badge>
          <Badge variant="secondary" className="px-2 py-0 text-[11px]">
            {retrievedChunkIds.length} getirilen kanıt
          </Badge>
        </div>
        <ChevronDown
          className={`h-4 w-4 shrink-0 text-slate-500 transition-transform duration-200 ${
            open ? "rotate-180" : ""
          }`}
        />
      </CollapsibleTrigger>

      <CollapsibleContent className="border-t border-slate-200/80 px-3.5 py-3 space-y-3">
        {hasLayeredEvidence && evidenceLayers ? (
          <div className="space-y-3">
            {renderLayerGroup(
              "Katman 1 — Kişisel CCO Kayıtları & Kesin SQLite/Python Hesapları",
              "Hastaya ait ölçüm, beyan ve eksik veri nedenleri",
              evidenceLayers.patient_cco,
              "default"
            )}
            {renderLayerGroup(
              "Katman 2 — SNOMED CT IPS Terminolojisi",
              "Yapısal kavram ve ilişki tanımı (tanı olasılığı değildir)",
              evidenceLayers.snomed_terminology,
              "outline"
            )}
            {renderLayerGroup(
              "Katman 3 — Genel Klinik Eğitim Sözlüğü",
              "Genel tıbbi kavram açıklaması (kişisel kayıt değildir)",
              evidenceLayers.general_knowledge,
              "secondary"
            )}
          </div>
        ) : (
          <div className="space-y-1.5">
            {allChunkIds.map((chunkId, index) => {
              const isCited = citedSet.has(chunkId);
              const isHighlighted = highlightedChunkId === chunkId;
              const rankIndex = retrievedChunkIds.indexOf(chunkId);

              return (
                <div
                  key={chunkId}
                  className={`flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2 text-xs transition-colors ${
                    isHighlighted
                      ? "border-teal-500 bg-teal-50/80 ring-1 ring-teal-500/30"
                      : isCited
                        ? "border-teal-200/90 bg-white"
                        : "border-slate-200/80 bg-white/60 text-slate-600"
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    <span className="font-mono text-[11px] text-slate-400">
                      #{rankIndex >= 0 ? rankIndex + 1 : index + 1}
                    </span>
                    <code className="font-mono text-xs font-semibold text-slate-900">
                      {chunkId}
                    </code>
                  </div>

                  <div className="flex items-center gap-1.5">
                    {rankIndex >= 0 && (
                      <Badge variant="outline" className="text-[11px] py-0">
                        BM25 Aday #{rankIndex + 1}
                      </Badge>
                    )}
                    {isCited ? (
                      <Badge variant="success" className="text-[11px] py-0">
                        <Check className="h-3 w-3" />
                        Yanıtta Alıntılandı
                      </Badge>
                    ) : (
                      <Badge variant="secondary" className="text-[11px] py-0">
                        Getirildi • Alıntılanmadı
                      </Badge>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        <div className="flex items-start gap-2 rounded-lg bg-slate-100/90 px-3 py-2 text-[11px] leading-relaxed text-slate-600">
          {hasLayeredEvidence ? (
            <GitBranch className="mt-0.5 h-3.5 w-3.5 shrink-0 text-teal-700" />
          ) : (
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-500" />
          )}
          <p>
            <span className="font-semibold text-slate-700">Katman Ayrımı ve Gizlilik:</span>{" "}
            Opak kaynak kimlikleri ve ham serbest metin notları API yanıtında sızdırılmaz;
            kişisel CCO kayıtları, SNOMED CT IPS ontolojisi ve genel eğitim sözlüğü birbirinden
            ayrı katmanlarda doğrulanır.
          </p>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
