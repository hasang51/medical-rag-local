import { useCallback, useEffect, useState } from "react";
import { fetchHealth, MedicalRagApiError } from "@/lib/api";
import type { ApiClientError, HealthResponse } from "@/types/api";

export interface HealthState {
  loading: boolean;
  data: HealthResponse | null;
  error: ApiClientError | null;
  checkedAt: Date | null;
  refresh: () => Promise<void>;
}

export function useHealthStatus(): HealthState {
  const [loading, setLoading] = useState<boolean>(true);
  const [data, setData] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<ApiClientError | null>(null);
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetchHealth();
      setData(response);
      setError(null);
      setCheckedAt(new Date());
    } catch (err) {
      setData(null);
      setCheckedAt(new Date());
      if (err instanceof MedicalRagApiError) {
        setError(err.info);
      } else {
        setError({
          kind: "backend_offline",
          status: null,
          detail: "Sağlık kontrolü başarısız oldu.",
        });
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { loading, data, error, checkedAt, refresh };
}
