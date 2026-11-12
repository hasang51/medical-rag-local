import type {
  ApiClientError,
  ChatRequest,
  ChatResponse,
  HealthResponse,
  PatientProfileItem,
  PatientsListResponse,
} from "@/types/api";

// FastAPI request_timeout_seconds=180.0 sn olduğundan istemci zaman aşımı 185 saniyedir.
const CHAT_CLIENT_TIMEOUT_MS = 185_000;
const HEALTH_CLIENT_TIMEOUT_MS = 6_000;

function extractFastApiDetail(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const record = payload as Record<string, unknown>;
  if (typeof record.detail === "string" && record.detail.trim()) {
    return record.detail.trim();
  }
  if (Array.isArray(record.detail) && record.detail.length > 0) {
    const messages = record.detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as Record<string, unknown>).msg);
        }
        return null;
      })
      .filter((msg): msg is string => Boolean(msg));
    if (messages.length > 0) {
      return messages.join("; ");
    }
  }
  return null;
}

export class MedicalRagApiError extends Error {
  public readonly info: ApiClientError;

  constructor(info: ApiClientError) {
    super(info.detail);
    this.name = "MedicalRagApiError";
    this.info = info;
  }
}

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), HEALTH_CLIENT_TIMEOUT_MS);

  const onExternalAbort = () => controller.abort();
  signal?.addEventListener("abort", onExternalAbort, { once: true });

  try {
    const response = await fetch("/health", {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });

    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try {
        const parsed: unknown = await response.json();
        detail = extractFastApiDetail(parsed) ?? detail;
      } catch {
        // Gövde JSON değilse durum kodu korunur (örn. Vite proxy 502/504).
      }
      throw new MedicalRagApiError({
        kind: response.status >= 500 ? "backend_offline" : "http_error",
        status: response.status,
        detail,
      });
    }

    const data = (await response.json()) as HealthResponse;
    return data;
  } catch (err) {
    if (err instanceof MedicalRagApiError) {
      throw err;
    }
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new MedicalRagApiError({
        kind: "timeout",
        status: null,
        detail: "Sağlık kontrolü zaman aşımına uğradı.",
      });
    }
    throw new MedicalRagApiError({
      kind: "backend_offline",
      status: null,
      detail: "Yerel FastAPI sunucusuna (127.0.0.1:8000) ulaşılamıyor.",
    });
  } finally {
    window.clearTimeout(timer);
    signal?.removeEventListener("abort", onExternalAbort);
  }
}

export async function fetchPatients(signal?: AbortSignal): Promise<PatientProfileItem[]> {
  try {
    const response = await fetch("/v1/patients", {
      method: "GET",
      headers: { Accept: "application/json" },
      signal,
    });
    if (!response.ok) {
      return [];
    }
    const payload = (await response.json()) as PatientsListResponse;
    return Array.isArray(payload.patients) ? payload.patients : [];
  } catch {
    return [];
  }
}

export async function postChat(
  request: ChatRequest,
  externalSignal?: AbortSignal
): Promise<ChatResponse> {
  const controller = new AbortController();
  let timedOutByClient = false;
  const timer = window.setTimeout(() => {
    timedOutByClient = true;
    controller.abort();
  }, CHAT_CLIENT_TIMEOUT_MS);

  const onExternalAbort = () => controller.abort();
  externalSignal?.addEventListener("abort", onExternalAbort, { once: true });

  try {
    const payloadBody: Record<string, unknown> = {
      question: request.question,
      top_k: request.top_k,
    };
    if (request.case_id) {
      payloadBody.case_id = request.case_id;
    }

    const response = await fetch("/v1/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(payloadBody),
      signal: controller.signal,
    });

    if (!response.ok) {
      let parsedBody: unknown = null;
      let rawText = "";
      try {
        rawText = await response.text();
        parsedBody = rawText ? JSON.parse(rawText) : null;
      } catch {
        parsedBody = null;
      }
      const fastApiDetail = extractFastApiDetail(parsedBody);

      if (response.status === 504) {
        throw new MedicalRagApiError({
          kind: "timeout",
          status: 504,
          detail: fastApiDetail ?? "model zaman aşımı",
        });
      }

      if (response.status === 503) {
        throw new MedicalRagApiError({
          kind: "model_unreachable",
          status: 503,
          detail: fastApiDetail ?? "model erişilemez",
        });
      }

      if (response.status === 422) {
        throw new MedicalRagApiError({
          kind: "validation",
          status: 422,
          detail: fastApiDetail ?? "Soru doğrulama sınırlarını karşılamıyor (1–500 karakter).",
        });
      }

      // Vite dev sunucusu FastAPI kapalıyken 502 veya boş 500 döndürebilir.
      if (response.status === 502 || (response.status === 500 && !fastApiDetail)) {
        throw new MedicalRagApiError({
          kind: "backend_offline",
          status: response.status,
          detail:
            "Yerel FastAPI sunucusuna (127.0.0.1:8000) bağlanılamadı. Sunucunun çalıştığından emin olun.",
        });
      }

      throw new MedicalRagApiError({
        kind: "http_error",
        status: response.status,
        detail: fastApiDetail ?? `Beklenmeyen sunucu hatası (HTTP ${response.status}).`,
      });
    }

    const payload = (await response.json()) as ChatResponse;
    return payload;
  } catch (err) {
    if (err instanceof MedicalRagApiError) {
      throw err;
    }
    if (err instanceof DOMException && err.name === "AbortError") {
      if (timedOutByClient) {
        throw new MedicalRagApiError({
          kind: "timeout",
          status: null,
          detail: "İstemci zaman aşımı (185 sn) aşıldı.",
        });
      }
      throw err;
    }
    throw new MedicalRagApiError({
      kind: "backend_offline",
      status: null,
      detail: "Ağ hatası veya FastAPI sunucusu (127.0.0.1:8000) kapalı.",
    });
  } finally {
    window.clearTimeout(timer);
    externalSignal?.removeEventListener("abort", onExternalAbort);
  }
}
