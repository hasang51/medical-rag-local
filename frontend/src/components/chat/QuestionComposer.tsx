import { useState, type FormEvent, type KeyboardEvent } from "react";
import { CornerDownLeft, Info, Loader2, SlidersHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";

const MAX_QUESTION_CHARS = 500;
const TOP_K_OPTIONS = [1, 2, 3, 4, 5] as const;

interface QuestionComposerProps {
  value: string;
  onChange: (value: string) => void;
  topK: number;
  onTopKChange: (topK: number) => void;
  onSubmit: (question: string, topK: number) => void;
  isSubmitting: boolean;
  selectedCaseId?: string | null;
}

export function QuestionComposer({
  value,
  onChange,
  topK,
  onTopKChange,
  onSubmit,
  isSubmitting,
  selectedCaseId = null,
}: QuestionComposerProps) {
  const [validationHint, setValidationHint] = useState<string | null>(null);

  const trimmedLength = value.trim().length;
  const rawLength = value.length;
  const isOverLimit = rawLength > MAX_QUESTION_CHARS;
  const canSubmit = !isSubmitting && trimmedLength >= 1 && !isOverLimit;

  const triggerSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed) {
      setValidationHint("Soru boş olamaz.");
      return;
    }
    if (value.length > MAX_QUESTION_CHARS) {
      setValidationHint(`Soru en fazla ${MAX_QUESTION_CHARS} karakter olabilir.`);
      return;
    }
    setValidationHint(null);
    onSubmit(trimmed, topK);
  };

  const handleFormSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!isSubmitting) {
      triggerSubmit();
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (canSubmit) {
        triggerSubmit();
      }
    }
  };

  return (
    <div className="sticky bottom-0 z-20 border-t border-slate-200/85 bg-gradient-to-t from-slate-50 via-slate-50/95 to-slate-50/80 px-4 pt-3 pb-4 backdrop-blur-sm">
      <form
        onSubmit={handleFormSubmit}
        className="mx-auto max-w-4xl rounded-2xl border border-slate-200 bg-white p-3 shadow-sm transition-shadow focus-within:border-teal-600/60 focus-within:ring-2 focus-within:ring-teal-600/15"
      >
        <textarea
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            if (validationHint) {
              setValidationHint(null);
            }
          }}
          onKeyDown={handleKeyDown}
          disabled={isSubmitting}
          rows={2}
          placeholder={
            selectedCaseId
              ? `${selectedCaseId} kaydına sorun: son uyku, HRV, baş ağrısı veya laboratuvar…`
              : "Genel sözlüğe Türkçe bir kavram sorusu yazın… (Örn: Nabız nedir?)"
          }
          aria-label="Tıbbi kavram sorusu"
          className="w-full resize-none bg-transparent px-1.5 py-1 text-sm leading-relaxed text-slate-900 placeholder:text-slate-400 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
        />

        {validationHint && (
          <p role="alert" className="px-1.5 pt-1 text-xs font-medium text-rose-600">
            {validationHint}
          </p>
        )}

        <div className="mt-2 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-2.5">
          <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
            <div className="flex items-center gap-1.5">
              <SlidersHorizontal className="h-3.5 w-3.5 text-slate-400" />
              <label htmlFor="top-k-select" className="font-medium text-slate-600">
                {selectedCaseId ? "Kanıt adedi:" : "BM25 top_k:"}
              </label>
              <select
                id="top-k-select"
                value={topK}
                disabled={isSubmitting}
                onChange={(e) => onTopKChange(Number(e.target.value))}
                className="rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 font-mono text-xs font-medium text-slate-800 focus:border-teal-600 focus:outline-none disabled:opacity-50"
              >
                {TOP_K_OPTIONS.map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
              </select>
            </div>

            <span className="hidden md:inline-flex items-center gap-1 text-[11px] text-slate-400">
              <Info className="h-3 w-3" />
              {selectedCaseId
                ? "Digital Twin: CCO + SNOMED + genel sözlük. Önceki tur gönderilmez."
                : "Genel sözlük turu. Önceki sorular yeni isteğe aktarılmaz."}
            </span>
          </div>

          <div className="flex items-center gap-3">
            <span
              className={`font-mono text-xs ${
                isOverLimit
                  ? "font-semibold text-rose-600"
                  : rawLength > MAX_QUESTION_CHARS * 0.85
                    ? "text-amber-600"
                    : "text-slate-400"
              }`}
            >
              {rawLength}/{MAX_QUESTION_CHARS}
            </span>

            <Button type="submit" size="sm" disabled={!canSubmit}>
              {isSubmitting ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span>Yanıt Bekleniyor…</span>
                </>
              ) : (
                <>
                  <span>Sorgula</span>
                  <CornerDownLeft className="h-3.5 w-3.5 opacity-80" />
                </>
              )}
            </Button>
          </div>
        </div>
      </form>
    </div>
  );
}
