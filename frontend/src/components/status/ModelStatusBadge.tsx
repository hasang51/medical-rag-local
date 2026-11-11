import { AlertTriangle, CheckCircle2, Loader2, RefreshCw, Unplug } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { HealthState } from "@/hooks/useHealthStatus";

const TARGET_26B_MODEL = "gemma4:26b-a4b-it-q4_K_M";

interface ModelStatusBadgeProps {
  health: HealthState;
}

export function ModelStatusBadge({ health }: ModelStatusBadgeProps) {
  const { loading, data, error, checkedAt, refresh } = health;

  const timeLabel = checkedAt
    ? checkedAt.toLocaleTimeString("tr-TR", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
    : null;

  if (loading && !data && !error) {
    return (
      <Badge variant="secondary" className="py-1 px-3">
        <Loader2 className="h-3.5 w-3.5 animate-spin text-slate-500" />
        <span>Model durumu doğrulanıyor…</span>
      </Badge>
    );
  }

  // FastAPI erişilemez
  if (error || !data) {
    return (
      <div className="inline-flex items-center gap-1.5">
        <TooltipProvider delayDuration={150}>
          <Tooltip>
            <TooltipTrigger asChild>
              <div>
                <Badge variant="danger" className="py-1 px-3 cursor-default">
                  <Unplug className="h-3.5 w-3.5" />
                  <span>FastAPI Kapalı</span>
                </Badge>
              </div>
            </TooltipTrigger>
            <TooltipContent side="bottom" align="end">
              <p className="font-medium">GET /health yanıt vermedi</p>
              <p className="mt-0.5 text-slate-300">
                {error?.detail ?? "127.0.0.1:8000 üzerinde FastAPI sunucusunu başlatın."}
              </p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => void refresh()}
          disabled={loading}
          aria-label="Model durumunu yenile"
          title="Model durumunu yenile"
          className="h-7 w-7 text-slate-500"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
        </Button>
      </div>
    );
  }

  const isOllamaOk = data.status === "ok" && data.ollama === "ok";
  const isTarget26B = data.model === TARGET_26B_MODEL;

  // Ollama / SSH tüneli erişilemez (status: degraded, ollama: unreachable)
  if (!isOllamaOk) {
    return (
      <div className="inline-flex items-center gap-1.5">
        <TooltipProvider delayDuration={150}>
          <Tooltip>
            <TooltipTrigger asChild>
              <div>
                <Badge variant="warning" className="py-1 px-3 cursor-default">
                  <AlertTriangle className="h-3.5 w-3.5" />
                  <span>Ollama Erişilemez</span>
                  <span className="font-mono text-[11px] opacity-80">({data.model})</span>
                </Badge>
              </div>
            </TooltipTrigger>
            <TooltipContent side="bottom" align="end">
              <p className="font-medium">
                /health: status={data.status}, ollama={data.ollama}
              </p>
              <p className="mt-0.5 text-slate-300">
                Yerel SSH tünelinin (127.0.0.1:11435) ve RunPod Ollama servisinin açık olduğunu kontrol edin.
              </p>
              {timeLabel && <p className="mt-1 text-[11px] text-slate-400">Son kontrol: {timeLabel}</p>}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => void refresh()}
          disabled={loading}
          aria-label="Model durumunu yenile"
          title="Model durumunu yenile"
          className="h-7 w-7 text-slate-500"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
        </Button>
      </div>
    );
  }

  // Gemma 4 26B doğrulandı
  if (isTarget26B) {
    return (
      <div className="inline-flex items-center gap-1.5">
        <TooltipProvider delayDuration={150}>
          <Tooltip>
            <TooltipTrigger asChild>
              <div>
                <Badge variant="default" className="py-1 px-3 cursor-default">
                  <span className="h-2 w-2 rounded-full bg-teal-600" />
                  <span className="font-semibold">Gemma 4 26B</span>
                  <span className="hidden md:inline font-mono text-[11px] text-teal-700/85">
                    {data.model}
                  </span>
                </Badge>
              </div>
            </TooltipTrigger>
            <TooltipContent side="bottom" align="end">
              <p className="font-medium flex items-center gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                Canlı /health doğrulaması başarılı
              </p>
              <p className="mt-0.5 font-mono text-[11px] text-slate-300">
                model={data.model} • ollama={data.ollama}
              </p>
              {timeLabel && <p className="mt-1 text-[11px] text-slate-400">Son kontrol: {timeLabel}</p>}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => void refresh()}
          disabled={loading}
          aria-label="Model durumunu yenile"
          title="Model durumunu yenile"
          className="h-7 w-7 text-slate-500"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
        </Button>
      </div>
    );
  }

  // FastAPI farklı bir modelle (ör. varsayılan gemma4:e4b) yapılandırılmış
  return (
    <div className="inline-flex items-center gap-1.5">
      <TooltipProvider delayDuration={150}>
        <Tooltip>
          <TooltipTrigger asChild>
            <div>
              <Badge variant="warning" className="py-1 px-3 cursor-default">
                <AlertTriangle className="h-3.5 w-3.5" />
                <span>Aktif Model:</span>
                <span className="font-mono text-[11px]">{data.model}</span>
              </Badge>
            </div>
          </TooltipTrigger>
          <TooltipContent side="bottom" align="end">
            <p className="font-medium">Gemma 4 26B yerine {data.model} yapılandırılmış</p>
            <p className="mt-0.5 text-slate-300">
              26B için FastAPI&apos;yi{" "}
              <code className="font-mono text-[11px]">
                MEDICAL_RAG_MODEL={TARGET_26B_MODEL}
              </code>{" "}
              ve{" "}
              <code className="font-mono text-[11px]">
                MEDICAL_RAG_OLLAMA_BASE_URL=http://127.0.0.1:11435
              </code>{" "}
              ile başlatın.
            </p>
            {timeLabel && <p className="mt-1 text-[11px] text-slate-400">Son kontrol: {timeLabel}</p>}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
      <Button
        variant="ghost"
        size="icon"
        onClick={() => void refresh()}
        disabled={loading}
        aria-label="Model durumunu yenile"
        title="Model durumunu yenile"
        className="h-7 w-7 text-slate-500"
      >
        <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
      </Button>
    </div>
  );
}
