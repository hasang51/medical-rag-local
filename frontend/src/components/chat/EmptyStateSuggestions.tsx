import { ArrowUpRight, BookOpenCheck, ShieldCheck, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { SUGGESTED_QUESTIONS, type SuggestedQuestion } from "@/data/suggestedQuestions";

interface EmptyStateSuggestionsProps {
  onSelectQuestion: (question: string) => void;
  disabled?: boolean;
}

export function EmptyStateSuggestions({
  onSelectQuestion,
  disabled = false,
}: EmptyStateSuggestionsProps) {
  return (
    <section aria-label="Örnek sentetik derlem soruları" className="space-y-6 py-4">
      <div className="rounded-2xl border border-slate-200/90 bg-white p-6 shadow-2xs sm:p-8">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="default">
            <BookOpenCheck className="h-3.5 w-3.5" />
            <span>Sentetik Tıbbi Derlem</span>
          </Badge>
          <Badge variant="outline">
            <ShieldCheck className="h-3.5 w-3.5 text-teal-700" />
            <span>Alıntı Zorunlu Güvenlik Sözleşmesi</span>
          </Badge>
        </div>

        <h2 className="mt-4 text-xl font-semibold tracking-tight text-slate-900 sm:text-2xl">
          Kaynağa Bağlı Tıbbi Kavram Sorgulama
        </h2>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-600">
          Bu arayüz, yerel BM25 sözlük getiricisi ve FastAPI güvenlik katmanı üzerinden çalışır.
          Her soru bağımsız (<span className="font-medium text-slate-800">tek turlu</span>) olarak
          değerlendirilir; kaynak parçada karşılığı olmayan veya klinik rol/doz iddiası içeren
          çıktılar otomatik olarak güvenli çekimserliğe düşürülür.
        </p>

        <div className="mt-6">
          <div className="mb-3 flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500">
              <Sparkles className="h-3.5 w-3.5 text-teal-700" />
              Sentetik Derlemden Örnek Sorular
            </span>
            <span className="text-xs text-slate-400">Sorgulamak için bir kart seçin</span>
          </div>

          <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
            {SUGGESTED_QUESTIONS.map((item: SuggestedQuestion) => (
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
                  item.isOutOfScopeDemo
                    ? "border-amber-200/80 bg-amber-50/30 hover:border-amber-300 hover:bg-amber-50/60"
                    : "border-slate-200/90 bg-slate-50/40 hover:border-teal-300 hover:bg-teal-50/30"
                } ${disabled ? "pointer-events-none opacity-50" : "cursor-pointer"}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span
                    className={`text-[11px] font-semibold ${
                      item.isOutOfScopeDemo ? "text-amber-800" : "text-teal-800"
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
