import { useCallback, useEffect, useState } from "react";
import type { SessionTurn } from "@/types/api";

const SESSION_STORAGE_KEY = "medical_rag_session_turns_v1";
const DIAGNOSTICS_PREF_KEY = "medical_rag_show_diagnostics_v1";

function loadTurnsFromSession(): SessionTurn[] {
  try {
    const raw = window.sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed as SessionTurn[];
  } catch {
    return [];
  }
}

export function useSessionHistory() {
  const [turns, setTurns] = useState<SessionTurn[]>(() => loadTurnsFromSession());
  const [showDiagnostics, setShowDiagnostics] = useState<boolean>(() => {
    try {
      return window.sessionStorage.getItem(DIAGNOSTICS_PREF_KEY) === "true";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try {
      window.sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(turns));
    } catch {
      // sessionStorage kotası dolarsa sessizce geç.
    }
  }, [turns]);

  useEffect(() => {
    try {
      window.sessionStorage.setItem(
        DIAGNOSTICS_PREF_KEY,
        showDiagnostics ? "true" : "false"
      );
    } catch {
      // Yoksay
    }
  }, [showDiagnostics]);

  const appendTurn = useCallback((turn: SessionTurn) => {
    setTurns((prev) => [...prev, turn]);
  }, []);

  const clearHistory = useCallback(() => {
    setTurns([]);
    try {
      window.sessionStorage.removeItem(SESSION_STORAGE_KEY);
    } catch {
      // Yoksay
    }
  }, []);

  return {
    turns,
    appendTurn,
    clearHistory,
    showDiagnostics,
    setShowDiagnostics,
  };
}
