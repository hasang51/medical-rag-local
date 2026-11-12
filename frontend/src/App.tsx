import { useEffect, useRef, useState } from "react";
import { EmptyStateSuggestions } from "@/components/chat/EmptyStateSuggestions";
import { PendingTurnCard } from "@/components/chat/PendingTurnCard";
import { QueryTurnCard } from "@/components/chat/QueryTurnCard";
import { QuestionComposer } from "@/components/chat/QuestionComposer";
import { HeaderBar } from "@/components/layout/HeaderBar";
import { MedicalDisclaimerBanner } from "@/components/safety/MedicalDisclaimerBanner";
import {
  SUGGESTED_QUESTIONS,
  TWIN_SUGGESTED_QUESTIONS,
} from "@/data/suggestedQuestions";
import { useHealthStatus } from "@/hooks/useHealthStatus";
import { useSessionHistory } from "@/hooks/useSessionHistory";
import { fetchPatients, MedicalRagApiError, postChat } from "@/lib/api";
import type { ChatRequest, PatientProfileItem } from "@/types/api";

interface PendingTurnState {
  request: ChatRequest;
  startedAtMs: number;
}

export function App() {
  const health = useHealthStatus();
  const {
    turns,
    appendTurn,
    clearHistory,
    showDiagnostics,
    setShowDiagnostics,
  } = useSessionHistory();

  const [patients, setPatients] = useState<PatientProfileItem[]>([]);
  const [patientsError, setPatientsError] = useState<string | null>(null);
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(
    "oracle-pilot-001"
  );
  const [questionInput, setQuestionInput] = useState<string>("");
  const [topK, setTopK] = useState<number>(3);
  const [pendingTurn, setPendingTurn] = useState<PendingTurnState | null>(null);

  const bottomAnchorRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void fetchPatients(controller.signal).then((items) => {
      if (controller.signal.aborted) {
        return;
      }
      setPatients(items);
      setPatientsError(
        items.length === 0
          ? "Hasta profilleri yüklenemedi. FastAPI (127.0.0.1:8000) kapalı olabilir."
          : null
      );
    });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (pendingTurn || turns.length > 0) {
      bottomAnchorRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [pendingTurn, turns.length]);

  const handleSubmitQuestion = async (
    question: string,
    selectedTopK: number,
    explicitCaseId?: string | null
  ) => {
    if (pendingTurn) {
      return;
    }

    const activeCaseId =
      explicitCaseId !== undefined ? explicitCaseId : selectedCaseId;

    const request: ChatRequest = {
      question: question.trim(),
      top_k: selectedTopK,
      ...(activeCaseId ? { case_id: activeCaseId } : {}),
    };

    setQuestionInput("");
    setPendingTurn({ request, startedAtMs: Date.now() });

    const turnId =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `turn-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

    try {
      const response = await postChat(request);
      appendTurn({
        id: turnId,
        createdAtIso: new Date().toISOString(),
        request,
        response,
      });
    } catch (err) {
      const errorInfo =
        err instanceof MedicalRagApiError
          ? err.info
          : {
              kind: "backend_offline" as const,
              status: null,
              detail: "Beklenmeyen istemci hatası oluştu.",
            };

      appendTurn({
        id: turnId,
        createdAtIso: new Date().toISOString(),
        request,
        error: errorInfo,
      });

      setQuestionInput(request.question);
      void health.refresh();
    } finally {
      setPendingTurn(null);
    }
  };

  const isSubmitting = pendingTurn !== null;
  const chipQuestions = selectedCaseId
    ? TWIN_SUGGESTED_QUESTIONS
    : SUGGESTED_QUESTIONS.slice(0, 5);

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-900">
      <MedicalDisclaimerBanner selectedCaseId={selectedCaseId} />

      <HeaderBar
        health={health}
        patients={patients}
        selectedCaseId={selectedCaseId}
        onSelectCaseId={setSelectedCaseId}
        showDiagnostics={showDiagnostics}
        onToggleDiagnostics={setShowDiagnostics}
        turnCount={turns.length}
        onClearHistory={clearHistory}
        disabled={isSubmitting}
      />

      <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col px-4 py-6">
        {patientsError && (
          <p
            role="alert"
            className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900"
          >
            {patientsError}
          </p>
        )}
        {turns.length === 0 && !pendingTurn ? (
          <EmptyStateSuggestions
            selectedCaseId={selectedCaseId}
            onSelectQuestion={(q) => void handleSubmitQuestion(q, topK)}
            disabled={isSubmitting}
          />
        ) : (
          <div className="space-y-5 pb-6">
            <div className="flex items-center gap-2 overflow-x-auto pb-1">
              <span className="shrink-0 text-xs font-medium text-slate-400">
                Örnekler:
              </span>
              {chipQuestions.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  disabled={isSubmitting}
                  onClick={() => void handleSubmitQuestion(item.question, topK)}
                  className="shrink-0 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-600 transition-colors hover:border-teal-300 hover:bg-teal-50/50 hover:text-teal-900 disabled:pointer-events-none disabled:opacity-50 cursor-pointer"
                >
                  {item.category}
                </button>
              ))}
            </div>

            {turns.map((turn, idx) => (
              <QueryTurnCard
                key={turn.id}
                turn={turn}
                turnNumber={idx + 1}
                showDiagnostics={showDiagnostics}
                onRetryOrReuse={(q, k, cid) => {
                  setTopK(k);
                  void handleSubmitQuestion(q, k, cid);
                }}
                isSubmitting={isSubmitting}
              />
            ))}

            {pendingTurn && (
              <PendingTurnCard
                request={pendingTurn.request}
                startedAtMs={pendingTurn.startedAtMs}
              />
            )}

            <div ref={bottomAnchorRef} />
          </div>
        )}
      </main>

      <QuestionComposer
        value={questionInput}
        onChange={setQuestionInput}
        topK={topK}
        onTopKChange={setTopK}
        onSubmit={(q, k) => void handleSubmitQuestion(q, k)}
        isSubmitting={isSubmitting}
        selectedCaseId={selectedCaseId}
      />
    </div>
  );
}

export default App;
