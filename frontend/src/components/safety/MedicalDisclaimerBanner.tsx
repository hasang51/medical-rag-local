import { ShieldAlert } from "lucide-react";

export const DEFAULT_MEDICAL_DISCLAIMER =
  "Bu yanıt eğitim amaçlıdır; tanı, tedavi veya doz önerisi değildir.";

export function MedicalDisclaimerBanner() {
  return (
    <div
      role="note"
      aria-label="Tıbbi sorumluluk reddi"
      className="border-b border-teal-900/10 bg-teal-50/70 px-4 py-2 text-xs text-teal-950"
    >
      <div className="mx-auto flex max-w-4xl items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <ShieldAlert className="h-3.5 w-3.5 shrink-0 text-teal-700" />
          <p className="leading-relaxed">
            <span className="font-semibold">Klinik Güvenlik Notu:</span>{" "}
            {DEFAULT_MEDICAL_DISCLAIMER} Yalnızca sentetik eğitim derlemi kullanılır; acil veya kişisel sağlık kararları için hekime başvurun.
          </p>
        </div>
        <span className="hidden sm:inline-block shrink-0 rounded border border-teal-200 bg-white/80 px-2 py-0.5 font-mono text-[10px] font-medium text-teal-800">
          SENTETİK DERLEM • TEK TURLU RAG
        </span>
      </div>
    </div>
  );
}
