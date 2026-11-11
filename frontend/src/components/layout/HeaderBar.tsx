import { Activity, Stethoscope, Trash2 } from "lucide-react";
import { ModelStatusBadge } from "@/components/status/ModelStatusBadge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import type { HealthState } from "@/hooks/useHealthStatus";

interface HeaderBarProps {
  health: HealthState;
  showDiagnostics: boolean;
  onToggleDiagnostics: (next: boolean) => void;
  turnCount: number;
  onClearHistory: () => void;
  disabled?: boolean;
}

export function HeaderBar({
  health,
  showDiagnostics,
  onToggleDiagnostics,
  turnCount,
  onClearHistory,
  disabled = false,
}: HeaderBarProps) {
  return (
    <header className="sticky top-0 z-30 border-b border-slate-200/80 bg-white/95 backdrop-blur-md">
      <div className="mx-auto flex max-w-4xl flex-wrap items-center justify-between gap-3 px-4 py-3.5">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-teal-700 text-white shadow-xs">
            <Stethoscope className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-semibold tracking-tight text-slate-900 sm:text-lg">
                Medical RAG
              </h1>
              <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-600">
                Klinik Sözlük
              </span>
            </div>
            <p className="text-xs text-slate-500">
              Kaynağa bağlı Türkçe tıbbi kavram doğrulama arayüzü
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2.5 sm:gap-3">
          <ModelStatusBadge health={health} />

          <label
            htmlFor="diagnostics-toggle"
            className="flex cursor-pointer items-center gap-2 rounded-lg border border-slate-200 bg-slate-50/80 px-2.5 py-1.5 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-100"
          >
            <Activity className="h-3.5 w-3.5 text-teal-700" />
            <span className="hidden sm:inline">Tanılama</span>
            <Switch
              id="diagnostics-toggle"
              checked={showDiagnostics}
              onCheckedChange={onToggleDiagnostics}
              aria-label="Geliştirici tanılama verilerini göster"
            />
          </label>

          {turnCount > 0 && (
            <Button
              variant="outline"
              size="sm"
              onClick={onClearHistory}
              disabled={disabled}
              className="text-slate-600"
              title="Mevcut tarayıcı oturumu geçmişini temizle"
            >
              <Trash2 className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Oturumu Temizle</span>
              <span className="rounded bg-slate-100 px-1.5 py-0.2 font-mono text-[11px] text-slate-600">
                {turnCount}
              </span>
            </Button>
          )}
        </div>
      </div>
    </header>
  );
}
