"""Tek tur duman ölçümü. Model çağrısı sırasında tepe RAM'i yazar.

Çıkış kodu 3: sistem belleği yaklaşık 14 GiB çizgisini aştı. Bu durumda E4B
bırakılır; daha küçük etikete geçiş ayrıca onay ister.
"""

import json
import subprocess
import threading
import time
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from medical_rag.config import Settings
from medical_rag.main import create_app

# Plan: sistem dahil yaklaşık 14 GB altında kalmak.
MEMORY_LIMIT_BYTES = 14 * 1024**3
SMOKE_PROMPT = "Yanıt olarak yalnızca şu cümleyi yaz: Sentetik duman testi basarili."

_SAMPLE = r"""
$os = Get-CimInstance Win32_OperatingSystem
$ollama = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -like 'ollama*' -or $_.ProcessName -eq 'llama-server' }
$ws = 0
if ($ollama) { $ws = ($ollama | Measure-Object WorkingSet64 -Sum).Sum }
[pscustomobject]@{
  ollama_working_set_bytes = [int64]$ws
  used_physical_bytes = [int64](($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) * 1KB)
  total_physical_bytes = [int64]($os.TotalVisibleMemorySize * 1KB)
} | ConvertTo-Json -Compress
"""


def sample_memory() -> dict[str, int]:
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", _SAMPLE],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    return {key: int(payload[key]) for key in payload}


def run_smoke(settings: Settings | None = None) -> dict[str, object]:
    settings = settings or Settings()
    samples: list[dict[str, int]] = []
    stop = threading.Event()

    def poll() -> None:
        while not stop.is_set():
            try:
                samples.append(sample_memory())
            except (subprocess.CalledProcessError, json.JSONDecodeError, OSError):
                pass
            stop.wait(1.0)

    try:
        samples.append(sample_memory())
    except (subprocess.CalledProcessError, json.JSONDecodeError, OSError):
        pass
    thread = threading.Thread(target=poll, daemon=True)
    thread.start()
    started = time.perf_counter()
    try:
        with TestClient(create_app(settings)) as client:
            client.timeout = httpx.Timeout(settings.request_timeout_seconds + 5)
            response = client.post("/v1/complete", json={"prompt": SMOKE_PROMPT})
    finally:
        stop.set()
        thread.join(timeout=5)
        try:
            samples.append(sample_memory())
        except (subprocess.CalledProcessError, json.JSONDecodeError, OSError):
            pass
    elapsed = time.perf_counter() - started
    response.raise_for_status()
    body = response.json()
    peak_used = max((item["used_physical_bytes"] for item in samples), default=0)
    peak_ollama = max((item["ollama_working_set_bytes"] for item in samples), default=0)
    return {
        "elapsed_seconds": elapsed,
        "num_ctx": body["num_ctx"],
        "model": body["model"],
        "text_nonempty": bool(str(body["text"]).strip()),
        "eval_count": body["eval_count"],
        "eval_duration_ns": body["eval_duration_ns"],
        "peak_used_physical_bytes": peak_used,
        "peak_ollama_working_set_bytes": peak_ollama,
        "memory_limit_bytes": MEMORY_LIMIT_BYTES,
        "within_memory_limit": peak_used <= MEMORY_LIMIT_BYTES,
        "sample_count": len(samples),
    }


def write_smoke(payload: dict[str, object], directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "smoke_ram.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> None:
    settings = Settings()
    payload = run_smoke(settings)
    path = write_smoke(payload, settings.runtime_dir)
    print(path)
    if int(payload["sample_count"]) < 1 or int(payload["peak_used_physical_bytes"]) <= 0:
        raise SystemExit(2)
    if not payload["text_nonempty"] or payload["num_ctx"] != settings.num_ctx:
        raise SystemExit(2)
    if float(payload["elapsed_seconds"]) > settings.request_timeout_seconds:
        raise SystemExit(2)
    if not payload["within_memory_limit"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
