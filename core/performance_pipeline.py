import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import ui_events
from .contracts import (
    AnalysisPhase,
    AnalysisResultPayload,
    AnalysisStatus,
    BatchProgressEvent,
    CancellationState,
    FastAnalyzer,
    IdentityAnalyzer,
    ProgressCallback,
)

UiEventQueue = ui_events.UiEventQueue

FAST_OK = "FAST_OK"
NEEDS_OCR = "NEEDS_OCR"
NEEDS_REVIEW = "NEEDS_REVIEW"
OCR_OK = "OCR_OK"
ERROR = "ERROR"

FAST_MODE = "fast"
DEEP_MODE = "deep"

OCR_CAPABLE_EXTENSIONS = {
    ".epub",
    ".mobi",
    ".azw",
    ".azw3",
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".tif",
    ".tiff",
    ".bmp",
    ".webp",
}


@dataclass
class AnalysisResult:
    original_path: str
    format: str
    status: AnalysisStatus
    title: str = ""
    author: str = ""
    year: str = ""
    isbn: str = ""
    confidence: float = 0
    primary_method: str = ""
    identity_result: dict = field(default_factory=dict)
    error: str = ""

    def as_dict(self) -> AnalysisResultPayload:
        return asdict(self)


def supports_deferred_ocr(path: str | Path) -> bool:
    return Path(path).suffix.lower() in OCR_CAPABLE_EXTENSIONS


def final_status(identity_result: dict[str, Any] | None, *, used_ocr: bool = False) -> AnalysisStatus:
    result = dict(identity_result or {})
    if result.get("error"):
        return ERROR
    if result.get("encontrado"):
        return OCR_OK if used_ocr else FAST_OK
    return NEEDS_REVIEW


def light_worker_count(requested: int | None = None) -> int:
    default = min(8, max(4, os.cpu_count() or 4))
    return max(1, min(8, int(requested or default)))


def ocr_worker_count(requested: int | None = None) -> int:
    return max(1, min(2, int(requested or 1)))


def _parallel_batch(
    items: list[Path],
    worker: FastAnalyzer,
    *,
    max_workers: int,
    phase: AnalysisPhase,
    event_callback: ProgressCallback | None = None,
    cancellation: CancellationState | None = None,
) -> list[AnalysisResultPayload]:
    indexed_items = list(enumerate(items))
    results = [None] * len(indexed_items)
    if not indexed_items:
        return results

    completed = 0
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix=f"myl-{phase}") as executor:
        futures = {}
        for index, item in indexed_items:
            if cancellation and cancellation.cancelled:
                break
            futures[executor.submit(worker, item)] = (index, item)
        for future in as_completed(futures):
            if cancellation and cancellation.cancelled:
                for pending in futures:
                    pending.cancel()
                break
            index, item = futures[future]
            try:
                results[index] = future.result()
            # This is the isolation boundary for third-party parsers and user
            # supplied analyzers. A single malformed book must not abort the
            # rest of the batch, regardless of its exception type.
            except Exception as exc:  # noqa: BLE001
                results[index] = make_analysis_result(item, ERROR, error=str(exc))
            completed += 1
            if event_callback:
                event: BatchProgressEvent = {
                    "phase": phase,
                    "completed": completed,
                    "total": len(indexed_items),
                    "path": str(item),
                    "status": results[index].get("status", ERROR),
                }
                event_callback(event)
    return [result for result in results if result is not None]


def process_fast_batch(
    paths: list[Path],
    analyzer: FastAnalyzer,
    *,
    max_workers: int | None = None,
    event_callback: ProgressCallback | None = None,
    cancellation: CancellationState | None = None,
) -> list[AnalysisResultPayload]:
    return _parallel_batch(
        [Path(path) for path in paths],
        analyzer,
        max_workers=light_worker_count(max_workers),
        phase="fast",
        event_callback=event_callback,
        cancellation=cancellation,
    )


def process_ocr_batch(
    analysis_results: list[AnalysisResultPayload],
    analyzer: IdentityAnalyzer,
    *,
    max_workers: int | None = None,
    event_callback: ProgressCallback | None = None,
    cancellation: CancellationState | None = None,
) -> list[AnalysisResultPayload]:
    pending = [
        Path(result["original_path"])
        for result in analysis_results
        if result.get("status") == NEEDS_OCR and result.get("original_path")
    ]

    def resolve(path):
        identity = dict(analyzer(Path(path)) or {})
        return make_analysis_result(
            path,
            final_status(identity, used_ocr=True),
            title=identity.get("titulo", ""),
            author=identity.get("autor", ""),
            year=identity.get("anio", ""),
            isbn=identity.get("isbn", ""),
            confidence=identity.get("confianza", 0),
            primary_method="deferred_ocr",
            identity_result=identity,
            error=identity.get("error", ""),
        )

    return _parallel_batch(
        pending,
        resolve,
        max_workers=ocr_worker_count(max_workers),
        phase="ocr",
        event_callback=event_callback,
        cancellation=cancellation,
    )


def make_analysis_result(
    path,
    status: AnalysisStatus,
    *,
    title="",
    author="",
    year="",
    isbn="",
    confidence=0,
    primary_method="",
    identity_result=None,
    error="",
) -> AnalysisResultPayload:
    original = Path(path)
    return AnalysisResult(
        original_path=str(original),
        format=original.suffix.lower(),
        status=status,
        title=str(title or ""),
        author=str(author or ""),
        year=str(year or ""),
        isbn=str(isbn or ""),
        confidence=float(confidence or 0),
        primary_method=str(primary_method or ""),
        identity_result=dict(identity_result or {}),
        error=str(error or ""),
    ).as_dict()
