import argparse
import json
from dataclasses import dataclass
from pathlib import Path


ACCEPTED_STATUSES = {"ACCEPTED", "FAST_OK", "OCR_OK"}
QUALITY_WARNING = (
    "No se certifican clics reales de UI sin control del escritorio. "
    "Completar performance_visual_checklist.md antes del merge."
)


@dataclass
class Difference:
    severity: str
    path: str
    detail: str


def _load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _records(snapshot: dict) -> dict[str, dict]:
    return {item["relative_path"]: item for item in snapshot.get("records", [])}


def _accepted(record: dict) -> bool:
    return bool(record.get("found")) or record.get("status") in ACCEPTED_STATUSES


def _confidence(record: dict) -> float:
    return float(record.get("confidence", 0) or 0)


def _metadata_losses(path: str, baseline: dict, candidate: dict) -> list[Difference]:
    losses = []
    for field in ("title", "author", "year", "isbn"):
        if baseline.get(field) and not candidate.get(field):
            losses.append(Difference("RISK", path, f"Candidate lost baseline {field}: {baseline[field]!r}."))
    return losses


def compare_quality(baseline: dict, candidate: dict, *, threshold=90.0) -> list[Difference]:
    differences = []
    baseline_records = _records(baseline)
    candidate_records = _records(candidate)
    for path, base in baseline_records.items():
        current = candidate_records.get(path)
        if current is None:
            differences.append(Difference("RISK", path, "Candidate result is missing."))
            continue
        if current.get("error"):
            differences.append(Difference("RISK", path, f"Candidate returned an error: {current['error']}"))
        if _accepted(current) and _confidence(current) < threshold:
            differences.append(Difference("RISK", path, f"Candidate accepted low confidence {_confidence(current):.1f} < {threshold:.1f}."))
        if _accepted(current) and (not current.get("title") or not current.get("author")):
            differences.append(Difference("RISK", path, "Candidate accepted an incomplete title/author identity."))
        differences.extend(_metadata_losses(path, base, current))
        if _accepted(base) and not _accepted(current):
            differences.append(Difference("CONSERVATIVE", path, "Candidate sends a previously accepted file to review."))
        elif not _accepted(base) and _accepted(current):
            if _confidence(current) >= threshold and current.get("title") and current.get("author"):
                differences.append(Difference("IMPROVEMENT", path, "Candidate accepts the file with complete high-confidence evidence."))
            else:
                differences.append(Difference("RISK", path, "Candidate accepts a file that baseline kept for review without stronger evidence."))
        elif current.get("status") == "FAST_OK" and base.get("ocr_used"):
            if _confidence(current) >= threshold and current.get("title") and current.get("author"):
                differences.append(Difference("IMPROVEMENT", path, "Candidate safely avoids baseline OCR with complete high-confidence metadata."))
            else:
                differences.append(Difference("RISK", path, "Candidate skipped baseline OCR without complete high-confidence metadata."))

    for path in sorted(set(candidate_records) - set(baseline_records)):
        differences.append(Difference("INFO", path, "Candidate contains an additional result."))

    baseline_groups = baseline.get("duplicates", {}).get("exact_duplicate_groups", [])
    candidate_groups = candidate.get("duplicates", {}).get("exact_duplicate_groups", [])
    if baseline_groups != candidate_groups:
        differences.append(Difference("RISK", "*duplicates*", "Exact duplicate groups changed between baseline and candidate."))
    return differences


def compare_equivalence(sequential: dict, parallel: dict, *, confidence_tolerance=0.01) -> list[Difference]:
    differences = []
    sequential_records = _records(sequential)
    parallel_records = _records(parallel)
    for path, expected in sequential_records.items():
        actual = parallel_records.get(path)
        if actual is None:
            differences.append(Difference("RISK", path, "Parallel result is missing."))
            continue
        for field in ("status", "title", "author", "year", "isbn", "found", "sent_to_review"):
            if expected.get(field) != actual.get(field):
                differences.append(Difference("RISK", path, f"Parallel {field} differs: {expected.get(field)!r} != {actual.get(field)!r}."))
        if abs(_confidence(expected) - _confidence(actual)) > confidence_tolerance:
            differences.append(Difference("RISK", path, f"Parallel confidence differs: {_confidence(expected):.3f} != {_confidence(actual):.3f}."))
    for path in sorted(set(parallel_records) - set(sequential_records)):
        differences.append(Difference("RISK", path, "Parallel snapshot contains an unexpected result."))
    if sequential.get("duplicates") != parallel.get("duplicates"):
        differences.append(Difference("RISK", "*duplicates*", "Parallel duplicate groups differ from sequential groups."))
    return differences


def _section(lines: list[str], title: str, differences: list[Difference]):
    lines.extend([f"## {title}", ""])
    if not differences:
        lines.extend(["No differences detected.", ""])
        return
    lines.extend(["| Severity | Path | Detail |", "| --- | --- | --- |"])
    for item in differences:
        detail = item.detail.replace("|", "\\|")
        lines.append(f"| {item.severity} | `{item.path}` | {detail} |")
    lines.append("")


def write_report(path: Path, baseline: dict, candidate: dict, quality: list[Difference], equivalence: list[Difference]):
    risks = [item for item in quality + equivalence if item.severity == "RISK"]
    lines = [
        "# Quality regression report",
        "",
        f"- Baseline: `{baseline.get('label', '')}`",
        f"- Candidate: `{candidate.get('label', '')}`",
        f"- Files compared: `{baseline.get('files_total', 0)}`",
        f"- Baseline elapsed: `{baseline.get('elapsed_seconds', 0)} s`",
        f"- Candidate elapsed: `{candidate.get('elapsed_seconds', 0)} s`",
        f"- Blocking risks: `{len(risks)}`",
        "",
        f"> {QUALITY_WARNING}",
        "",
    ]
    _section(lines, "Baseline vs candidate", quality)
    _section(lines, "Sequential vs parallel candidate", equivalence)
    lines.extend([
        "## Decision",
        "",
        "**PASS**: no blocking quality regression detected." if not risks else "**FAIL**: correct blocking quality risks before opening a PR.",
        "",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Compare stable and candidate metadata quality snapshots.")
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--sequential")
    parser.add_argument("--parallel")
    parser.add_argument("--report", required=True)
    parser.add_argument("--threshold", type=float, default=90.0)
    args = parser.parse_args()

    baseline = _load(Path(args.baseline))
    candidate = _load(Path(args.candidate))
    quality = compare_quality(baseline, candidate, threshold=args.threshold)
    equivalence = []
    if args.sequential and args.parallel:
        equivalence = compare_equivalence(_load(Path(args.sequential)), _load(Path(args.parallel)))
    write_report(Path(args.report), baseline, candidate, quality, equivalence)

    for item in quality + equivalence:
        print(f"[{item.severity}] {item.path}: {item.detail}")
    risks = [item for item in quality + equivalence if item.severity == "RISK"]
    print(f"Blocking risks: {len(risks)}")
    print(f"Report: {Path(args.report).resolve()}")
    if risks:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
