/**
 * src/medical_rag/api/schemas.py ile birebir eşleşen API şema tipleri.
 * Yalnızca FastAPI'nin gerçekte kabul ettiği ve döndürdüğü alanlar yer alır.
 */

export interface ChatRequest {
  question: string;
  top_k: number;
  case_id?: string | null;
}

export interface EvidenceLayerItem {
  citation_id: string;
  layer: "patient_cco" | "snomed_terminology" | "general_knowledge" | string;
  title: string;
}

export interface EvidenceLayers {
  patient_cco: EvidenceLayerItem[];
  snomed_terminology: EvidenceLayerItem[];
  general_knowledge: EvidenceLayerItem[];
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
  case_id?: string | null;
  intent?: string;
  emergency?: boolean;
  emergency_category?: string | null;
  evidence_layers?: EvidenceLayers;
}

export interface PatientProfileItem {
  case_id: string;
  evaluated_at: string;
  has_structured_data: boolean;
  total_rows: number;
  value_fact_count: number;
  missing_result_count: number;
  families: string[];
}

export interface PatientsListResponse {
  patients: PatientProfileItem[];
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
