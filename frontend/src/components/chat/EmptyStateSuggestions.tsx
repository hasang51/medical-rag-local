import { ArrowUpRight, BookOpenCheck, ShieldCheck, Sparkles, UserCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import {
  SUGGESTED_QUESTIONS,
  TWIN_SUGGESTED_QUESTIONS,
  type SuggestedQuestion,
} from "@/data/suggestedQuestions";

interface EmptyStateSuggestionsProps {
  selectedCaseId?: string | null;
  onSelectQuestion: (question: string) => void;
  disabled?: boolean;
}

export function EmptyStateSuggestions({
  selectedCaseId = null,
  onSelectQuestion,
  disabled = false,
}: EmptyStateSuggestionsProps) {
  const activeQuestions = selectedCaseId ? TWIN_SUGGESTED_QUESTIONS : SUGGESTED_QUESTIONS;

  return (
    <section aria-label="Örnek sorgular" className="space-y-6 py-4">
      <div className="rounded-2xl border border-slate-200/90 bg-white p-6 shadow-2xs sm:p-8">
        <div className="flex flex-wrap items-center gap-2">
          {selectedCaseId ? (
            <Badge variant="default">
              <UserCheck className="h-3.5 w-3.5" />
              <span>Digital Twin Modu ({selectedCaseId})</span>
            </Badge>
          ) : (
            <Badge variant="default">
              <BookOpenCheck className="h-3.5 w-3.5" />
              <span>Sentetik Tıbbi Derlem</span>
            </Badge>
          )}
          <Badge variant="outline">
            <ShieldCheck className="h-3.5 w-3.5 text-teal-700" />
            <span>Model Öncesi Acil Durum & Alıntı Zorunlu Sözleşme</span>
          </Badge>
        </div>

        <h2 className="mt-4 text-xl font-semibold tracking-tight text-slate-900 sm:text-2xl">
          {selectedCaseId
            ? `${selectedCaseId} Kişisel CCO Kayıtları ve SNOMED CT IPS Asistanı`
            : "Kaynağa Bağlı Tıbbi Kavram Sorgulama"}
        </h2>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-600">
          {selectedCaseId
            ? "Sayısal özetler, son ölçümler ve eksik veri (data-required) nedenleri SQLite/Python ile kesin hesaplanır; semptomlar SNOMED CT IPS kavramlarıyla eşleştirilir ve kişisel kayıtlar genel eğitim bilgisinden ayrı tutulur."
            : "Bu arayüz, yerel BM25 sözlük getiricisi ve FastAPI güvenlik katmanı üzerinden çalışır. Üst çubuktan bir hasta profili seçerek G5 Digital Twin moduna geçebilirsiniz."}
        </p>

        <div className="mt-6">
          <div className="mb-3 flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500">
              <Sparkles className="h-3.5 w-3.5 text-teal-700" />
              {selectedCaseId ? "Digital Twin Örnek Hasta Soruları" : "Sentetik Derlemden Örnek Sorular"}
            </span>
            <span className="text-xs text-slate-400">Sorgulamak için bir kart seçin</span>
          </div>

          <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
            {activeQuestions.map((item: SuggestedQuestion) => (
              <Card
                key={item.id}
                role="button"
                tabIndex={disabled ? -1 : 0}
                aria-disabled={disabled}
                onClick={() => {
                  if (!disabled) {
                    onSelectQuestion(item.question);
                  }
                }}
                onKeyDown={(e) => {
                  if (!disabled && (e.key === "Enter" || e.key === " ")) {
                    e.preventDefault();
                    onSelectQuestion(item.question);
                  }
                }}
                className={`group flex flex-col justify-between rounded-xl border p-3.5 transition-all ${
                  item.isEmergencyDemo
                    ? "border-rose-200/90 bg-rose-50/40 hover:border-rose-300 hover:bg-rose-50/70"
                    : item.isOutOfScopeDemo
                      ? "border-amber-200/80 bg-amber-50/30 hover:border-amber-300 hover:bg-amber-50/60"
                      : "border-slate-200/90 bg-slate-50/40 hover:border-teal-300 hover:bg-teal-50/30"
                } ${disabled ? "pointer-events-none opacity-50" : "cursor-pointer"}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span
                    className={`text-[11px] font-semibold ${
                      item.isEmergencyDemo
                        ? "text-rose-800"
                        : item.isOutOfScopeDemo
                          ? "text-amber-800"
                          : "text-teal-800"
                    }`}
                  >
                    {item.category}
                  </span>
                  <ArrowUpRight className="h-3.5 w-3.5 text-slate-400 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-teal-700" />
                </div>
                <p className="mt-1.5 text-sm font-medium leading-snug text-slate-800">
                  {item.question}
                </p>
                <span className="mt-2 font-mono text-[11px] text-slate-400">
                  {item.corpusHint}
                </span>
              </Card>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
