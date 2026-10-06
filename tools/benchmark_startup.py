"""Measure repeatable source smoke-start latency and Python allocation peak."""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = "MYL_STARTUP_METRICS="


def _percentile_95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int(len(ordered) * 0.95 + 0.999) - 1))]


def benchmark_startup(repetitions: int = 5) -> dict:
    durations = []
    peaks = []
    program = (
        "import json,tracemalloc;"
        "tracemalloc.start();"
        "import main;"
        "code=main.smoke_test();"
        "current,peak=tracemalloc.get_traced_memory();"
        f"print('{MARKER}'+json.dumps({{'exit_code':code,'python_peak_bytes':peak}}))"
    )
    for _ in range(max(1, repetitions)):
        started = time.perf_counter()
        completed = subprocess.run(
            [sys.executable, "-c", program],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        durations.append((time.perf_counter() - started) * 1000)
        marker_line = next(
            (line for line in completed.stdout.splitlines() if line.startswith(MARKER)),
            "",
        )
        if completed.returncode or not marker_line:
            raise RuntimeError(completed.stderr or completed.stdout or "Startup benchmark failed")
        metrics = json.loads(marker_line.removeprefix(MARKER))
        if metrics["exit_code"]:
            raise RuntimeError("Source smoke test failed")
        peaks.append(metrics["python_peak_bytes"])
    return {
        "repetitions": len(durations),
        "startup_p50_ms": round(statistics.median(durations), 3),
        "startup_p95_ms": round(_percentile_95(durations), 3),
        "python_allocation_peak_mib": round(max(peaks) / (1024 * 1024), 3),
        "scope": "source smoke import; excludes Tk window creation and native process RSS",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = benchmark_startup(args.repetitions)
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    print(encoded)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
