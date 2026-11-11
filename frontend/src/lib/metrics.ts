/**
 * src/medical_rag/eval/report.py içindeki gerçek metrik türevleriyle birebir uyumludur.
 * Hiçbir metrik tahmin edilmez; yalnızca API'nin döndürdüğü alanlardan hesaplanır.
 */

// config.py içindeki varsayılan num_predict=128 tavanı (done_reason boş geldiğinde vekil kural).
const DEFAULT_NUM_PREDICT = 128;

export function tokensPerSecond(count: number, durationNs: number): number | null {
  if (count <= 0 || durationNs <= 0) {
    return null;
  }
  return count / (durationNs / 1_000_000_000);
}

export function isGenerationTruncated(
  evalCount: number,
  doneReason: string,
  numPredict: number = DEFAULT_NUM_PREDICT
): boolean {
  if (doneReason === "length") {
    return true;
  }
  if (doneReason === "stop" || evalCount <= 0) {
    return false;
  }
  return evalCount >= numPredict;
}

export function nsToMs(ns: number): number | null {
  if (ns <= 0) {
    return null;
  }
  return ns / 1_000_000;
}

export function formatDurationMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || Number.isNaN(ms)) {
    return "—";
  }
  if (ms < 1000) {
    return `${ms.toFixed(0)} ms`;
  }
  return `${(ms / 1000).toFixed(2)} sn`;
}

export function formatRate(rate: number | null): string {
  if (rate === null || Number.isNaN(rate)) {
    return "—";
  }
  return `${rate.toFixed(1)} tok/sn`;
}
