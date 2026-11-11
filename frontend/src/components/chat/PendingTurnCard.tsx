import { useEffect, useState } from "react";
import { Loader2, MessageSquareText } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import type { ChatRequest } from "@/types/api";

interface PendingTurnCardProps {
  request: ChatRequest;
  startedAtMs: number;
}

export function PendingTurnCard({ request, startedAtMs }: PendingTurnCardProps) {
  const [elapsedMs, setElapsedMs] = useState<number>(() => Date.now() - startedAtMs);

  useEffect(() => {
    const id = window.setInterval(() => {
      setElapsedMs(Date.now() - startedAtMs);
    }, 100);
    return () => window.clearInterval(id);
  }, [startedAtMs]);

  return (
    <Card className="border-teal-200/90 bg-white shadow-xs">
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
            <MessageSquareText className="h-3.5 w-3.5 text-teal-700" />
            <span>Tek Turlu Klinik Sorgu</span>
            <span className="font-mono text-[11px] text-slate-400">
              top_k={request.top_k}
            </span>
          </div>
          <Badge variant="default" className="font-mono text-[11px]">
            <Loader2 className="h-3 w-3 animate-spin" />
            <span>{(elapsedMs / 1000).toFixed(1)} sn</span>
          </Badge>
        </div>
        <p className="mt-1.5 text-base font-semibold leading-snug text-slate-900">
          {request.question}
        </p>
      </CardHeader>

      <CardContent className="space-y-3 pt-1">
        <div className="rounded-xl border border-slate-200/80 bg-slate-50/80 p-4">
          <div className="flex items-center gap-2.5 text-sm font-medium text-slate-700">
            <span className="h-2.5 w-2.5 rounded-full bg-teal-600 animate-subtle-pulse" />
            <span>
              BM25 sözlük getirimi ve kaynak doğrulamalı yanıt hazırlanıyor…
            </span>
          </div>
          <p className="mt-1.5 text-xs text-slate-500">
            Arka uç akışsız (<code className="font-mono">stream=False</code>) çalışır; yanıt
            ve güvenlik sözleşmesi tamamlandığında tek seferde gösterilecektir.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
