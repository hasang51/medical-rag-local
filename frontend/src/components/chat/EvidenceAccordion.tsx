import { Check, ChevronDown, FileSearch, Info } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

interface EvidenceAccordionProps {
  citations: string[];
  retrievedChunkIds: string[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  highlightedChunkId?: string | null;
}

export function EvidenceAccordion({
  citations,
  retrievedChunkIds,
  open,
  onOpenChange,
  highlightedChunkId,
}: EvidenceAccordionProps) {
  // Yalnızca API gerçekten citations veya retrieved_chunk_ids döndürdüğünde gösterilir.
  if (citations.length === 0 && retrievedChunkIds.length === 0) {
    return null;
  }

  const citedSet = new Set(citations);
  // Sıralamayı BM25'in döndürdüğü retrieved_chunk_ids üzerinden koru; olası ek alıntı varsa sona ekle.
  const allChunkIds = Array.from(new Set([...retrievedChunkIds, ...citations]));

  return (
    <Collapsible
      open={open}
      onOpenChange={onOpenChange}
      className="rounded-xl border border-slate-200/90 bg-slate-50/70"
    >
      <CollapsibleTrigger className="flex w-full items-center justify-between gap-3 px-3.5 py-2.5 text-left text-xs font-medium text-slate-700 transition-colors hover:bg-slate-100/80 rounded-xl cursor-pointer">
        <div className="flex flex-wrap items-center gap-2">
          <FileSearch className="h-4 w-4 text-teal-700" />
          <span className="font-semibold text-slate-800">
            RAG Kanıt ve Getirilen Parça Kimlikleri
          </span>
          <Badge variant="default" className="px-2 py-0 text-[11px]">
            {citations.length} doğrulanmış alıntı
          </Badge>
          <Badge variant="secondary" className="px-2 py-0 text-[11px]">
            {retrievedChunkIds.length} getirilen parça
          </Badge>
        </div>
        <ChevronDown
          className={`h-4 w-4 shrink-0 text-slate-500 transition-transform duration-200 ${
            open ? "rotate-180" : ""
          }`}
        />
      </CollapsibleTrigger>

      <CollapsibleContent className="border-t border-slate-200/80 px-3.5 py-3 space-y-3">
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

        <div className="flex items-start gap-2 rounded-lg bg-slate-100/90 px-3 py-2 text-[11px] leading-relaxed text-slate-600">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-500" />
          <p>
            <span className="font-semibold text-slate-700">Şeffaf API Sınırı:</span>{" "}
            <code className="font-mono">POST /v1/chat</code> yanıtı yalnızca doğrulanan{" "}
            <code className="font-mono">citations</code> ve BM25&apos;in getirdiği{" "}
            <code className="font-mono">retrieved_chunk_ids</code> kimliklerini döndürür; ham parça
            metni ve BM25 skoru API şemasında yer almadığından istemcide uydurulmaz. Alıntı
            bulunması klinik doğruluk kanıtlamaz.
          </p>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
