"""Reproducible benchmark for the catalog's interactive view model."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.library_view_model import LibraryViewIndex, cover_grid_positions

INTERACTION_BUDGET_MS = 100.0


def synthetic_catalog(size: int) -> list[dict]:
    extensions = (".epub", ".pdf", ".cbz", ".mobi")
    return [
        {
            "ruta": f"C:/Books/Author {index % 997}/Title {index}{extensions[index % 4]}",
            "nombre": f"Author {index % 997} - Title {index}{extensions[index % 4]}",
            "autor": f"Author {index % 997}",
            "extension": extensions[index % 4],
            "tamano_bytes": 500_000 + index,
            "serie": f"Series {index % 113}" if index % 3 == 0 else "",
            "tags": [f"tag-{index % 17}"],
            "isbn": f"978{index:010d}"[-13:],
            "mtime": 1_700_000_000 + index,
        }
        for index in range(size)
    ]


def _latency_ms(callback, repetitions: int) -> dict[str, float]:
    samples = []
    for _ in range(repetitions):
        started = time.perf_counter()
        callback()
        samples.append((time.perf_counter() - started) * 1000)
    ordered = sorted(samples)
    p95_index = min(len(ordered) - 1, max(0, int(len(ordered) * 0.95 + 0.999) - 1))
    return {
        "p50": round(statistics.median(ordered), 3),
        "p95": round(ordered[p95_index], 3),
    }


def benchmark_size(size: int, repetitions: int = 5, *, measure_memory: bool = False) -> dict:
    records = synthetic_catalog(size)
    started = time.perf_counter()
    view = LibraryViewIndex(records)
    prepare_ms = round((time.perf_counter() - started) * 1000, 3)
    search = _latency_ms(lambda: view.filter("Title 4242"), repetitions)
    format_filter = _latency_ms(lambda: view.filter(extension="pdf"), repetitions)
    all_items = _latency_ms(view.filter, repetitions)
    layout = _latency_ms(lambda: cover_grid_positions(30, 6), repetitions)
    measurements = {
        "size": size,
        "prepare_ms": prepare_ms,
        "search_p50_ms": search["p50"],
        "search_p95_ms": search["p95"],
        "format_filter_p50_ms": format_filter["p50"],
        "format_filter_p95_ms": format_filter["p95"],
        "all_items_p50_ms": all_items["p50"],
        "all_items_p95_ms": all_items["p95"],
        "cover_layout_p95_ms": layout["p95"],
        "visible_cover_widget_limit": 30,
    }
    if measure_memory:
        tracemalloc.start()
        memory_view = LibraryViewIndex(records)
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        measurements["prepared_view_peak_mib"] = round(peak / (1024 * 1024), 3)
        del memory_view
    measurements["interaction_budget_ms"] = INTERACTION_BUDGET_MS
    measurements["within_budget"] = all(
        measurements[key] <= INTERACTION_BUDGET_MS
        for key in ("search_p95_ms", "format_filter_p95_ms", "all_items_p95_ms")
    )
    return measurements


def run_benchmark(
    sizes: tuple[int, ...],
    repetitions: int = 5,
    *,
    measure_memory: bool = False,
) -> dict:
    return {
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor(),
        },
        "results": [
            benchmark_size(size, repetitions, measure_memory=measure_memory)
            for size in sizes
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", nargs="+", type=int, default=(1_000, 10_000, 50_000))
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--memory", action="store_true", help="Measure peak memory used by the prepared view")
    parser.add_argument("--check", action="store_true", help="Fail when an interaction exceeds 100 ms")
    args = parser.parse_args()
    report = run_benchmark(
        tuple(args.sizes),
        max(1, args.repetitions),
        measure_memory=args.memory,
    )
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    print(encoded)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    if args.check and not all(result["within_budget"] for result in report["results"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
