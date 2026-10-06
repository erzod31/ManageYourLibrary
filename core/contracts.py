"""Typed contracts shared by the analysis services and the UI coordinator.

The application still exposes dictionaries at its compatibility boundary.  The
types in this module make their required shape explicit without forcing a risky
all-at-once rewrite of existing callers.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Literal, Protocol, TypedDict

AnalysisStatus = Literal["FAST_OK", "NEEDS_OCR", "NEEDS_REVIEW", "OCR_OK", "ERROR"]
AnalysisPhase = Literal["fast", "ocr"]
IdentityResult = dict[str, Any]


class AnalysisResultPayload(TypedDict):
    original_path: str
    format: str
    status: AnalysisStatus
    title: str
    author: str
    year: str
    isbn: str
    confidence: float
    primary_method: str
    identity_result: IdentityResult
    error: str


class BatchProgressEvent(TypedDict):
    phase: AnalysisPhase
    completed: int
    total: int
    path: str
    status: AnalysisStatus


class CancellationState(Protocol):
    @property
    def cancelled(self) -> bool: ...


FastAnalyzer = Callable[[Path], AnalysisResultPayload]
IdentityAnalyzer = Callable[[Path], Mapping[str, Any] | None]
ProgressCallback = Callable[[BatchProgressEvent], None]
