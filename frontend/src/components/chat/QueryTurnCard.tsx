import { useState } from "react";
import {
  AlertOctagon,
  CheckCircle2,
  MessageSquareText,
  RotateCcw,
  ShieldAlert,
} from "lucide-react";
import { AbstentionCallout } from "@/components/chat/AbstentionCallout";
import { DiagnosticsPanel } from "@/components/chat/DiagnosticsPanel";
import { ErrorStateCard } from "@/components/chat/ErrorStateCard";
import { EvidenceAccordion } from "@/components/chat/EvidenceAccordion";
import { FormattedAnswer } from "@/components/chat/FormattedAnswer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { formatDurationMs } from "@/lib/metrics";
import type { SessionTurn } from "@/types/api";

interface QueryTurnCardProps {
  turn: SessionTurn;
  turnNumber: number;
  showDiagnostics: boolean;
  onRetryOrReuse: (question: string, topK: number, caseId?: string | null) => void;
  isSubmitting: boolean;
}

export function QueryTurnCard({
  turn,
  turnNumber,
  showDiagnostics,
  onRetryOrReuse,
  isSubmitting,
}: QueryTurnCardProps) {
  const { request, response, error, createdAtIso } = turn;
  const [evidenceOpen, setEvidenceOpen] = useState<boolean>(false);
  const [highlightedChunkId, setHighlightedChunkId] = useState<string | null>(null);

  const formattedTime = (() => {
    try {
      return new Date(createdAtIso).toLocaleTimeString("tr-TR", {
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return "";
    }
  })();

  const handleCitationClick = (chunkId: string) => {
    setHighlightedChunkId(chunkId);
    setEvidenceOpen(true);
  };

  const isEmergency = Boolean(response?.emergency);

  return (
    <Card
      className={`overflow-hidden transition-colors ${
        isEmergency ? "border-rose-300 ring-1 ring-rose-200" : ""
      }`}
    >
      <CardHeader className="pb-3.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <span className="inline-flex items-center gap-1 font-semibold text-teal-800">
              <MessageSquareText className="h-3.5 w-3.5 text-teal-700" />
              Sorgu #{turnNumber}
            </span>
            {formattedTime && <span>• {formattedTime}</span>}
            {request.case_id && (
              <span className="rounded bg-teal-50 border border-teal-200 px-1.5 py-0.5 font-mono text-[11px] font-medium text-teal-900">
                {request.case_id}
              </span>
            )}
            <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-600">
              top_k={request.top_k}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            {response && isEmergency && (
              <Badge variant="danger">
                <AlertOctagon className="h-3 w-3" />
                <span>112 Acil Durum Kapısı • Model Çağrılmadı</span>
              </Badge>
            )}
            {response && !isEmergency && !response.abstained && (
              <Badge variant="success">
                <CheckCircle2 className="h-3 w-3" />
                <span>Kaynak Doğrulandı ({response.citations.length})</span>
              </Badge>
            )}
            {response && !isEmergency && response.abstained && (
              <Badge variant="warning">Çekimser Yanıt</Badge>
            )}
            {response && (
              <Badge variant="outline" className="font-mono text-[11px]">
                {formatDurationMs(response.latency_ms)}
              </Badge>
            )}
          </div>
        </div>

        <h3 className="mt-2 text-base font-semibold leading-snug text-slate-900 sm:text-[17px]">
          {request.question}
        </h3>
      </CardHeader>

      <CardContent className="space-y-4">
        <Separator />

        {error && (
          <ErrorStateCard
            error={error}
            request={request}
            onRetry={(q, k) => onRetryOrReuse(q, k, request.case_id)}
            disabled={isSubmitting}
          />
        )}

        {response && (
          <>
            {isEmergency ? (
              <div
                role="alert"
                className="rounded-xl border border-rose-300 bg-rose-50/90 px-4 py-3.5 text-rose-950"
              >
                <div className="flex items-start gap-2.5">
                  <AlertOctagon className="mt-0.5 h-5 w-5 shrink-0 text-rose-700" />
                  <p className="text-sm font-medium leading-relaxed">{response.answer}</p>
                </div>
              </div>
            ) : response.abstained ? (
              <AbstentionCallout response={response} />
            ) : (
              <div className="rounded-xl border border-slate-100 bg-slate-50/40 px-4 py-3.5">
                <FormattedAnswer
                  answer={response.answer}
                  citations={response.citations}
                  onCitationClick={handleCitationClick}
                />
              </div>
            )}

            <EvidenceAccordion
              citations={response.citations}
              retrievedChunkIds={response.retrieved_chunk_ids}
              evidenceLayers={response.evidence_layers}
              open={evidenceOpen}
              onOpenChange={(next) => {
                setEvidenceOpen(next);
                if (!next) {
                  setHighlightedChunkId(null);
                }
              }}
              highlightedChunkId={highlightedChunkId}
            />

            {showDiagnostics && (
              <DiagnosticsPanel request={request} response={response} />
            )}

            <div className="flex flex-wrap items-center justify-between gap-2 pt-1 text-xs text-slate-500">
              <div className="flex items-center gap-1.5 text-slate-500">
                <ShieldAlert className="h-3.5 w-3.5 shrink-0 text-teal-700" />
                <span>{response.disclaimer}</span>
              </div>

              <Button
                variant="ghost"
                size="sm"
                disabled={isSubmitting}
                onClick={() => onRetryOrReuse(request.question, request.top_k, request.case_id)}
                className="h-7 px-2 text-xs text-slate-500 hover:text-slate-800"
                title="Bu soruyu giriş alanına kopyala veya tekrar gönder"
              >
                <RotateCcw className="h-3 w-3" />
                <span>Yeniden Sorgula</span>
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
