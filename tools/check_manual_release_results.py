import argparse
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

try:
    from tools.prepare_manual_release_validation import MARKER_NAME, REPO_ROOT, safe_validation_root
except ModuleNotFoundError:
    from prepare_manual_release_validation import MARKER_NAME, REPO_ROOT, safe_validation_root


MANUAL_CLICK_FORM = REPO_ROOT / "docs" / "manual_click_validation_form_windows.md"


@dataclass
class Check:
    name: str
    status: str
    detail: str


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest(root: Path) -> dict:
    marker = root / MARKER_NAME
    if not marker.is_file():
        raise RuntimeError(f"Validation marker not found: {marker}")
    return json.loads(marker.read_text(encoding="utf-8"))


def _find_hash(root: Path, expected_hash: str, size: int):
    matches = []
    for path in root.rglob("*"):
        if path.is_file() and path.stat().st_size == size and sha256(path) == expected_hash:
            matches.append(path)
    return matches


def _relative_paths(paths, root: Path):
    return ", ".join(sorted(path.relative_to(root).as_posix() for path in paths)) or "none"


def _fixture(manifest: dict, purpose: str):
    for item in manifest.get("fixtures", []):
        if item.get("purpose") == purpose:
            return item
    raise RuntimeError(f"Fixture purpose not found in manifest: {purpose}")


def _known_fixture_escapes(root: Path, manifest: dict):
    expected = {(item["sha256"], int(item["size"])) for item in manifest.get("fixtures", [])}
    escaped = []
    skipped = {".git", "dist", "tesseract", "__pycache__"}
    marked_roots = {
        marker.parent.resolve()
        for marker in REPO_ROOT.rglob(MARKER_NAME)
        if marker.is_file()
    }
    for path in REPO_ROOT.rglob("*"):
        resolved = path.resolve()
        if (
            not path.is_file()
            or any(part in skipped for part in path.relative_to(REPO_ROOT).parts)
            or any(resolved == marked_root or marked_root in resolved.parents for marked_root in marked_roots)
        ):
            continue
        size = path.stat().st_size
        candidates = [digest for digest, expected_size in expected if expected_size == size]
        if candidates and sha256(path) in candidates:
            escaped.append(path)
    return escaped


def _process_running():
    if os.name != "nt":
        return False
    run = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq ManageYourLibrary.exe", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        check=False,
    )
    return "ManageYourLibrary.exe" in run.stdout


def _read_manual_click_form(form_path: Path | None = None):
    path = Path(form_path) if form_path is not None else MANUAL_CLICK_FORM
    if not path.is_file():
        return None, f"Manual click form not found: {path}"
    try:
        return path.read_text(encoding="utf-8"), f"Manual click form: {path}"
    except OSError as exc:
        return None, f"Could not read manual click form {path}: {exc}"


def _manual_step_status(form_text: str | None, step_label: str, unavailable_detail: str):
    if form_text is None:
        return "PENDING", unavailable_detail

    pattern = re.compile(rf"\|\s*{re.escape(step_label)}\s*\|", re.IGNORECASE)
    matching_lines = [line for line in form_text.splitlines() if pattern.search(line)]
    if not matching_lines:
        return "PENDING", f"Manual checklist line not found: {step_label}."
    if len(matching_lines) > 1:
        return "FAIL", f"Ambiguous manual checklist: multiple lines found for {step_label}."

    line = matching_lines[0]
    ok_checked = bool(re.search(r"\[\s*x\s*\]\s*OK\b", line, re.IGNORECASE))
    fail_checked = bool(re.search(r"\[\s*x\s*\]\s*Fallo\b", line, re.IGNORECASE))
    if ok_checked and fail_checked:
        return "FAIL", f"Ambiguous manual checklist: both OK and Fallo are marked for {step_label}."
    if fail_checked:
        return "FAIL", f"Manual click-through marked Fallo for {step_label}."
    if ok_checked:
        return "PASS", f"Manual click-through marked OK for {step_label}."
    return "PENDING", f"Manual click-through is not marked yet for {step_label}."


def _manual_checks_from_form(form_path: Path | None = None):
    form_text, form_detail = _read_manual_click_form(form_path)
    undo_status, undo_detail = _manual_step_status(form_text, "6. Undo", form_detail)
    ocr_status, ocr_detail = _manual_step_status(form_text, "8. OCR image", form_detail)
    pdfium_status, pdfium_detail = _manual_step_status(form_text, "9. Scanned PDF", form_detail)

    if "FAIL" in (ocr_status, pdfium_status):
        frozen_status = "FAIL"
    elif ocr_status == pdfium_status == "PASS":
        frozen_status = "PASS"
    else:
        frozen_status = "PENDING"
    frozen_detail = f"{ocr_detail} {pdfium_detail}"

    return [
        Check("Undo button", undo_status, undo_detail),
        Check("Frozen OCR and PDFium buttons", frozen_status, frozen_detail),
    ]


def inspect_validation(root: Path) -> list[Check]:
    root = safe_validation_root(root)
    manifest = _load_manifest(root)
    checks = []

    required = ("appdata", "localappdata", "input", "library", "review", "ocr", "expected", "results")
    missing = [name for name in required if not (root / name).is_dir()]
    checks.append(Check("Temporary folder structure", "PASS" if not missing else "FAIL", "complete" if not missing else f"missing: {', '.join(missing)}"))

    config_path = root / "appdata" / "ManageYourLibrary" / "config.json"
    if config_path.is_file():
        try:
            configured = Path(json.loads(config_path.read_text(encoding="utf-8")).get("library", "")).resolve()
            expected = (root / "library").resolve()
            status = "PASS" if configured == expected else "FAIL"
            checks.append(Check("Isolated configured library", status, str(configured)))
        except Exception as exc:
            checks.append(Check("Isolated configured library", "FAIL", f"invalid config: {exc}"))
    else:
        checks.append(Check("Isolated configured library", "PENDING", "Open the launcher and select the temporary library in the UI."))

    add_fixture = _fixture(manifest, "Add books low-confidence fixture")
    add_matches = _find_hash(root, add_fixture["sha256"], int(add_fixture["size"]))
    library_matches = [path for path in add_matches if (root / "library") in path.parents]
    checks.append(Check(
        "Add books temporary move",
        "PASS" if library_matches else "PENDING",
        _relative_paths(library_matches or add_matches, root),
    ))

    trash = root / "library" / ".trash_manageyourlibrary"
    trash_files = [path for path in trash.rglob("*") if path.is_file() and path.name != "manifest.jsonl"] if trash.is_dir() else []
    trash_manifest = trash / "manifest.jsonl"
    quarantine_status = "PASS" if trash_files and trash_manifest.is_file() else "PENDING"
    checks.append(Check("Exact duplicate quarantine", quarantine_status, _relative_paths(trash_files, root)))
    checks.append(Check("Quarantine manifest", "PASS" if trash_manifest.is_file() else "PENDING", str(trash_manifest.relative_to(root))))

    search_fixture = _fixture(manifest, "Search metadata Unicode rename-in-place fixture")
    search_matches = _find_hash(root, search_fixture["sha256"], int(search_fixture["size"]))
    search_folder = root / "input" / "metadata_search"
    in_place = [path for path in search_matches if path.parent == search_folder]
    moved_to_library = [path for path in search_matches if (root / "library") in path.parents]
    original_name = Path(search_fixture["path"]).name
    if moved_to_library:
        checks.append(Check("Search metadata stays in place", "FAIL", _relative_paths(moved_to_library, root)))
    elif in_place and any(path.name != original_name for path in in_place):
        checks.append(Check("Search metadata stays in place", "PASS", _relative_paths(in_place, root)))
    elif in_place:
        checks.append(Check("Search metadata stays in place", "PENDING", "Fixture remains in its original folder but has not been renamed yet."))
    else:
        checks.append(Check("Search metadata stays in place", "FAIL", "Unicode metadata fixture is missing."))

    escaped = _known_fixture_escapes(root, manifest)
    checks.append(Check("Known fixtures stay inside temporary root", "PASS" if not escaped else "FAIL", _relative_paths(escaped, REPO_ROOT)))
    checks.append(Check("No residual frozen EXE process", "FAIL" if _process_running() else "PASS", "Close the app before running this checker."))
    checks.extend(_manual_checks_from_form())
    return checks


def write_report(root: Path, checks: list[Check]) -> Path:
    report = root / "results" / "manual_release_results.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Local frozen EXE manual-validation results",
        "",
        f"Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        f"Temporary root: `{root}`",
        "",
        "| Check | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for check in checks:
        detail = check.detail.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {check.name} | **{check.status}** | {detail} |")
    lines.extend([
        "",
        "This local report complements the human checklist. It does not claim that Tkinter buttons were clicked.",
    ])
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description="Inspect temporary results after the frozen EXE click-through.")
    parser.add_argument("--root", default="manual_release_validation", help="Validation folder inside the repository.")
    args = parser.parse_args()

    root = safe_validation_root(args.root)
    checks = inspect_validation(root)
    report = write_report(root, checks)
    for check in checks:
        print(f"[{check.status}] {check.name}: {check.detail}")
    print()
    print(f"Local report: {report}")
    if any(check.status == "FAIL" for check in checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
