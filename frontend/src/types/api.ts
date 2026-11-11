/**
 * src/medical_rag/api/schemas.py ile birebir eşleşen API şema tipleri.
 * Yalnızca FastAPI'nin gerçekte kabul ettiği ve döndürdüğü alanlar yer alır.
 */

export interface ChatRequest {
  question: string;
  top_k: number;
}

export interface ChatResponse {
  answer: string;
  citations: string[];
  abstained: boolean;
  disclaimer: string;
  eval_count: number;
  eval_duration_ns: number;
  total_duration_ns: number;
  done_reason: string;
  latency_ms: number;
  retrieved_chunk_ids: string[];
  load_duration_ns: number;
  prompt_eval_count: number;
  prompt_eval_duration_ns: number;
}

export interface HealthResponse {
  status: string;
  ollama: string;
  model: string;
}

export type ApiErrorKind =
  | "timeout"
  | "model_unreachable"
  | "validation"
  | "backend_offline"
  | "http_error";

export interface ApiClientError {
  kind: ApiErrorKind;
  status: number | null;
  detail: string;
}

export interface SessionTurn {
  id: string;
  createdAtIso: string;
  request: ChatRequest;
  response?: ChatResponse;
  error?: ApiClientError;
}
