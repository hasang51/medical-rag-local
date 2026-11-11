import { ShieldOff } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { ChatResponse } from "@/types/api";

interface AbstentionCalloutProps {
  response: ChatResponse;
}

export function AbstentionCallout({ response }: AbstentionCalloutProps) {
  // routes.py satır 82-100: hits boşsa model çağrılmaz (retrieved_chunk_ids=[], eval_count=0).
  // routes.py satır 113: hits var ama enforce_contract çekimserliğe düşürdüyse retrieved_chunk_ids doludur.
  const skippedModel =
    response.retrieved_chunk_ids.length === 0 && response.eval_count === 0;

  return (
    <div className="rounded-xl border border-amber-200/90 bg-amber-50/60 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-amber-900">
          <ShieldOff className="h-4 w-4 shrink-0 text-amber-700" />
          <span className="text-sm font-semibold">Güvenli Çekimserlik Kararı</span>
        </div>
        <Badge variant="warning">
          {skippedModel
            ? "BM25 Eşik Altı • Model Çağrılmadı"
            : "Güvenlik Sözleşmesi • Alıntı/Rol Koruması"}
        </Badge>
      </div>

      <p className="mt-2 text-sm font-medium leading-relaxed text-amber-950">
        {response.answer}
      </p>

      <p className="mt-1.5 text-xs leading-relaxed text-amber-800/90">
        {skippedModel
          ? "Sorgu terimleri sentetik eğitim derleminde BM25 eşiğinin (1.0) üzerinde eşleşme üretmediği için dil modeli çalıştırılmadan güvenli çekimser yanıt döndürüldü."
          : "BM25 aday parça getirdi ancak model yanıtı doğrulanabilir parça alıntısı içermediği veya klinik rol/doz sınırına girdiği için güvenlik politikası tarafından çekimser metne düşürüldü."}
      </p>
    </div>
  );
}
