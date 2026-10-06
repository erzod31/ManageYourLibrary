"""Kindle/MOBI/AZW identity helpers for local, non-DRM-breaking analysis."""

from __future__ import annotations

from pathlib import Path

from book_identity_evidence import IdentityEvidence, evidence_from_existing_data
from front_matter_analyzer import analyze_front_matter


KINDLE_FORMATS = {".mobi", ".azw", ".azw3"}


def build_kindle_identity_evidence(path: Path, datos=None, front_text: str = "") -> list[IdentityEvidence]:
    evidence = evidence_from_existing_data(datos or {}, filename=Path(path).name)
    if front_text:
        evidence.extend(analyze_front_matter(front_text, source="kindle_front_matter"))
    return evidence
