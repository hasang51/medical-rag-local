import { AlertCircle, Clock, RotateCcw, ServerCrash, WifiOff } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { ApiClientError, ChatRequest } from "@/types/api";

interface ErrorStateCardProps {
  error: ApiClientError;
  request: ChatRequest;
  onRetry: (question: string, topK: number) => void;
  disabled?: boolean;
}

export function ErrorStateCard({
  error,
  request,
  onRetry,
  disabled = false,
}: ErrorStateCardProps) {
  const config = (() => {
    switch (error.kind) {
      case "timeout":
        return {
          icon: Clock,
          title: "Model Zaman Aşımı (HTTP 504)",
          badge: error.status ? `HTTP ${error.status}` : "Zaman Aşımı",
          hint: "Uzak GPU modelinin yüklenmesi veya yanıt üretmesi zaman aşımı sınırını aştı. RunPod üzerindeki Ollama sürecini kontrol edip tekrar deneyebilirsiniz.",
        };
      case "model_unreachable":
        return {
          icon: ServerCrash,
          title: "Dil Modeline Ulaşılamıyor (HTTP 503)",
          badge: "HTTP 503",
          hint: "FastAPI çalışıyor ancak yerel SSH tüneline (127.0.0.1:11435) veya uzak RunPod Ollama servisine erişemiyor.",
        };
      case "validation":
        return {
          icon: AlertCircle,
          title: "İstek Doğrulama Hatası (HTTP 422)",
          badge: "HTTP 422",
          hint: "Soru boş olmamalı ve en fazla 500 karakter uzunluğunda olmalıdır.",
        };
      case "backend_offline":
        return {
          icon: WifiOff,
          title: "FastAPI Sunucusuna Bağlanılamadı",
          badge: error.status ? `HTTP ${error.status}` : "Bağlantı Yok",
          hint: "Yerel FastAPI sunucusunun 127.0.0.1:8000 adresinde çalıştığını doğrulayın.",
        };
      default:
        return {
          icon: AlertCircle,
          title: "Sorgu Tamamlanamadı",
          badge: error.status ? `HTTP ${error.status}` : "Hata",
          hint: "İstek işlenirken beklenmeyen bir hata oluştu.",
        };
    }
  })();

  const Icon = config.icon;

  return (
    <div
      role="alert"
      className="rounded-xl border border-rose-200/90 bg-rose-50/60 p-4 text-rose-950"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 shrink-0 text-rose-700" />
          <span className="text-sm font-semibold">{config.title}</span>
        </div>
        <Badge variant="danger" className="font-mono text-[11px]">
          {config.badge}
        </Badge>
      </div>

      <p className="mt-2 font-mono text-xs text-rose-900 bg-white/80 border border-rose-200/70 rounded-lg px-2.5 py-1.5">
        {error.detail}
      </p>

      <p className="mt-2 text-xs leading-relaxed text-rose-800/90">{config.hint}</p>

      {error.kind !== "validation" && (
        <div className="mt-3 flex justify-end">
          <Button
            variant="outline"
            size="sm"
            disabled={disabled}
            onClick={() => onRetry(request.question, request.top_k)}
            className="border-rose-200 bg-white text-rose-800 hover:bg-rose-50"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            <span>Bu Soruyu Yeniden Dene</span>
          </Button>
        </div>
      )}
    </div>
  );
}
