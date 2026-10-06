"""Convert external bibliographic candidates into Deep Identity evidence.

This module does not perform network calls. It only normalizes already-returned
candidate dictionaries into short, auditable evidence signals.
"""

from __future__ import annotations

from book_identity_evidence import IdentityEvidence, make_evidence


ALLOWED_EXTERNAL_SOURCES = {
    "Open Library",
    "Wikidata",
    "Library of Congress",
    "Crossref",
    "OpenAlex",
}


def candidate_to_evidence(candidate: dict) -> list[IdentityEvidence]:
    candidate = candidate or {}
    source = str(candidate.get("fuente") or candidate.get("source") or "external_source")
    if source not in ALLOWED_EXTERNAL_SOURCES:
        source = "external_source"
    evidence: list[IdentityEvidence] = []
    fields = [
        ("title", candidate.get("titulo") or candidate.get("title"), 78),
        ("author", candidate.get("autor") or candidate.get("author"), 76),
        ("year", candidate.get("anio") or candidate.get("year"), 48),
        ("isbn", candidate.get("isbn"), 92),
    ]
    for field_name, value, weight in fields:
        ev = make_evidence(field_name, value, source, weight, location="external candidate")
        if ev:
            evidence.append(ev)
    return evidence


def candidates_to_evidence(candidates) -> list[IdentityEvidence]:
    evidence: list[IdentityEvidence] = []
    for candidate in candidates or []:
        evidence.extend(candidate_to_evidence(candidate))
    return evidence
