import { Cpu, Gauge, Timer } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  formatDurationMs,
  formatRate,
  isGenerationTruncated,
  nsToMs,
  tokensPerSecond,
} from "@/lib/metrics";
import type { ChatRequest, ChatResponse } from "@/types/api";

interface DiagnosticsPanelProps {
  request: ChatRequest;
  response: ChatResponse;
}

export function DiagnosticsPanel({ request, response }: DiagnosticsPanelProps) {
  const genRate = tokensPerSecond(response.eval_count, response.eval_duration_ns);
  const promptRate = tokensPerSecond(
    response.prompt_eval_count,
    response.prompt_eval_duration_ns
  );
  const truncated = isGenerationTruncated(response.eval_count, response.done_reason);

  const metrics = [
    {
      label: "Uçtan Uca Gecikme (latency_ms)",
      value: formatDurationMs(response.latency_ms),
    },
    {
      label: "Toplam Ollama Süresi (total_duration_ns)",
      value: formatDurationMs(nsToMs(response.total_duration_ns)),
    },
    {
      label: "Model Yükleme (load_duration_ns)",
      value: formatDurationMs(nsToMs(response.load_duration_ns)),
    },
    {
      label: "İstem Değerlendirme (prompt_eval)",
      value:
        response.prompt_eval_count > 0
          ? `${response.prompt_eval_count} tok • ${formatDurationMs(nsToMs(response.prompt_eval_duration_ns))} (${formatRate(promptRate)})`
          : "0 tok",
    },
    {
      label: "Yanıt Üretimi (eval_count / eval_duration_ns)",
      value:
        response.eval_count > 0
          ? `${response.eval_count} tok • ${formatDurationMs(nsToMs(response.eval_duration_ns))} (${formatRate(genRate)})`
          : "0 tok (model çağrılmadı)",
    },
    {
      label: "Bitiş Nedeni (done_reason)",
      value: response.done_reason || "—",
    },
    {
      label: "BM25 top_k / Getirilen",
      value: `top_k=${request.top_k} → ${response.retrieved_chunk_ids.length} parça`,
    },
    {
      label: "Doğrulanan Alıntı Sayısı",
      value: `${response.citations.length}`,
    },
  ];

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-900 text-slate-100 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-2.5">
        <div className="flex items-center gap-2 text-xs font-semibold text-teal-300">
          <Cpu className="h-3.5 w-3.5" />
          <span>Geliştirici Tanılama Metrikleri (Gerçek API Yanıtı)</span>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <Badge className="border-slate-700 bg-slate-800 text-slate-200 font-mono text-[11px]">
            <Timer className="h-3 w-3 text-teal-400" />
            {formatDurationMs(response.latency_ms)}
          </Badge>
          {genRate !== null && (
            <Badge className="border-slate-700 bg-slate-800 text-slate-200 font-mono text-[11px]">
              <Gauge className="h-3 w-3 text-teal-400" />
              {formatRate(genRate)}
            </Badge>
          )}
          {truncated && (
            <Badge variant="warning" className="font-mono text-[11px]">
              Kesildi (num_predict tavanı)
            </Badge>
          )}
        </div>
      </div>

      <dl className="mt-3 grid grid-cols-1 gap-2.5 sm:grid-cols-2">
        {metrics.map((m) => (
          <div
            key={m.label}
            className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2"
          >
            <dt className="text-[11px] text-slate-400">{m.label}</dt>
            <dd className="mt-0.5 font-mono text-xs font-medium text-slate-100">
              {m.value}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
