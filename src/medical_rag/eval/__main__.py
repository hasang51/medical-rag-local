import json
import os
from pathlib import Path

from medical_rag.config import ROOT, Settings
from medical_rag.eval.report import (
    assert_acceptance,
    comparison_report,
    cpu_gpu_comparison,
    refuse_baseline_overwrite,
    run_eval,
    snapshot_before,
    write_csv,
    write_report,
)


def main() -> None:
    settings = Settings()
    baseline_env = os.environ.get("MEDICAL_RAG_BASELINE_REPORT", "").strip()
    if baseline_env:
        _run_against_baseline(settings, Path(baseline_env))
        return
    before = snapshot_before(settings.runtime_dir)
    payload = run_eval(settings)
    path = write_report(payload, settings.runtime_dir)
    assert_acceptance(payload)
    print(path)
    if before is not None:
        compared = comparison_report(before, payload)
        comparison_path = settings.runtime_dir / "latency_comparison.json"
        comparison_path.write_text(
            json.dumps(compared, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(comparison_path)


def _run_against_baseline(settings: Settings, baseline_path: Path) -> None:
    """Aynı soru turunu ayrı klasöre yazar. Baseline dosyaları yalnız okunur."""
    baseline_dir = (ROOT / "data" / "runtime").resolve()
    if settings.runtime_dir.resolve() == baseline_dir:
        raise SystemExit("GPU turu için MEDICAL_RAG_RUNTIME_DIR ayrı bir klasör olmalı")
    report_path = settings.runtime_dir / "eval_report.json"
    csv_path = settings.runtime_dir / "eval_report.csv"
    comparison_path = settings.runtime_dir / "cpu_vs_gpu.json"
    for path in (report_path, csv_path, comparison_path):
        refuse_baseline_overwrite(path, baseline_dir)
    if report_path.resolve() == baseline_path.resolve():
        raise SystemExit("GPU raporu CPU baseline dosyasının üzerine yazılamaz")

    payload = run_eval(settings)
    written = write_report(payload, settings.runtime_dir)
    records = payload["records"]
    if not isinstance(records, list):
        raise RuntimeError("rapor biçimi bozuk")
    write_csv([record for record in records if isinstance(record, dict)], csv_path)
    questions = json.loads(settings.questions_path.read_text(encoding="utf-8"))
    if not isinstance(questions, list):
        raise RuntimeError("soru dosyası bozuk")
    cpu_payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    compared = cpu_gpu_comparison(
        cpu_payload,
        payload,
        [item for item in questions if isinstance(item, dict)],
        cpu_source=baseline_path.name,
        gpu_source=written.name,
    )
    comparison_path.write_text(
        json.dumps(compared, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    assert_acceptance(payload)
    print(written)
    print(csv_path)
    print(comparison_path)


if __name__ == "__main__":
    main()
