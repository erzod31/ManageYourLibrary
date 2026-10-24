"""Package existing validated Windows builds; delegate compilation to platform scripts."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.write_build_manifest import sha256, source_tree_fingerprint
from tools.first_use_self_test import REQUIRED_CHECKS as FIRST_USE_CHECKS

PRIVATE_NAMES = {"config.json", "library_index.json", "library_history.csv", "historial.csv",
                 "undo_log.jsonl", "file_transactions.jsonl", "trash_manifest.jsonl",
                 "saved_views.json", "profile-manifest.json", ".profile.lock"}
PRIVATE_SUFFIXES = {".db", ".jsonl", ".csv", ".log", ".gguf", ".part",
                    ".epub", ".pdf", ".mobi", ".azw", ".azw3", ".djvu",
                    ".fb2", ".rtf", ".doc", ".docx", ".odt", ".cbr", ".cbz"}


def validate_payload(folder: Path, *, version: str, fingerprint: dict) -> dict:
    executable = folder / "ManageYourLibrary.exe"
    manifest = json.loads((folder / "build-manifest.json").read_text(encoding="utf-8"))
    runtime = json.loads((folder / "runtime-self-test.json").read_text(encoding="utf-8"))
    first_use = json.loads((folder / "first-use-self-test.json").read_text(encoding="utf-8"))
    if manifest["version"] != version or runtime["version"] != version or first_use["version"] != version:
        raise ValueError("Build and runtime versions must match VERSION")
    if manifest["source_tree"] != fingerprint:
        raise ValueError("Build fingerprint does not match current sources; rebuild first")
    if manifest["sha256"] != sha256(executable):
        raise ValueError("Executable no longer matches the recorded SHA-256")
    for gate in ("automated_tests", "source_smoke", "catalog_performance_gate",
                 "frozen_smoke", "runtime_self_test", "first_use_self_test"):
        if manifest["validation"].get(gate) != "passed":
            raise ValueError(f"Missing automated build gate: {gate}")
    expected_checks = {"tk_init", "bundled_languages", "image_ocr", "pdfium_ocr", "reader_isolation"}
    if (runtime.get("passed") is not True or runtime.get("frozen") is not True
            or set(runtime.get("checks", {})) != expected_checks
            or any(value != "passed" for value in runtime["checks"].values())):
        raise ValueError("Frozen runtime tests are incomplete or failed")
    if (first_use.get("passed") is not True or first_use.get("frozen") is not True
            or set(first_use.get("checks", {})) != FIRST_USE_CHECKS
            or any(value != "passed" for value in first_use["checks"].values())):
        raise ValueError("Frozen first-use tests are incomplete or failed")
    for path in folder.rglob("*"):
        name = path.name.lower()
        if path.is_symlink():
            raise ValueError(f"Symlink is not a release payload: {path.name}")
        if (name in PRIVATE_NAMES or ".sqlite" in name or path.suffix.lower() in PRIVATE_SUFFIXES
                or name.startswith(("metadata_cache", "ocr_cache", "analysis_cache"))
                or name in {".trash_manageyourlibrary", "ui_thumbnails", "__pycache__", "test_reports", "backups"}):
            raise ValueError(f"Personal state or cache in release payload: {path.name}")
    return manifest


def package(root: Path = ROOT, *, folder=None, installer=None, release=None, development=False) -> list[Path]:
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    folder = Path(folder) if folder else root / "dist" / "windows" / "ManageYourLibrary"
    installer = Path(installer) if installer else root / "dist" / "installer" / f"ManageYourLibrary-{version}-Setup-x64.exe"
    manifest = validate_payload(folder, version=version, fingerprint=source_tree_fingerprint())
    if not development and manifest.get('validation', {}).get('redistribution_review') != 'passed':
        raise ValueError('Redistribution review is incomplete; only an explicit --development package is allowed')
    label = version + ('-development' if development else '')
    if not installer.is_file():
        raise ValueError("Compile the matching installer with BUILD_INSTALLER.bat first")
    if installer.stat().st_mtime < (folder / "ManageYourLibrary.exe").stat().st_mtime:
        raise ValueError("Installer is older than the application; rebuild the installer")
    release = Path(release) if release else root / "dist" / "release"
    release.mkdir(parents=True, exist_ok=True)
    if any(release.iterdir()):
        raise FileExistsError('Release output must be empty; existing packages will not be replaced')
    archive = release / f"ManageYourLibrary-{label}-Windows-x64-portable.zip"
    temporary = archive.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as target:
        if development:
            target.writestr('DEVELOPMENT-ONLY.txt',
                'Local validation build, not approved for public redistribution.\n'
                'Use a new --profile directory; do not open migrated profiles with older versions.\n'
                'See THIRD_PARTY_NOTICES.md for the incomplete native dependency review.\n')
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                target.write(path, (Path(folder.name) / path.relative_to(folder)).as_posix())
    with zipfile.ZipFile(temporary) as target:
        bad = target.testzip()
        if bad:
            raise ValueError(f"Portable CRC failed: {bad}")
    os.replace(temporary, archive)
    copied_installer = release / (installer.name.replace('-Setup-', '-development-Setup-') if development else installer.name)
    shutil.copy2(installer, copied_installer)
    provenance = release / f"build-manifest-{label}.json"
    shutil.copy2(folder / "build-manifest.json", provenance)
    artifacts = [archive, copied_installer, provenance]
    checksums = release / f"SHA256SUMS-{label}.txt"
    checksums.write_text("".join(f"{sha256(path)}  {path.name}\n" for path in artifacts), encoding="utf-8")
    print(json.dumps({"version": version, "source_commit": manifest["git_commit"],
                      "artifacts": [str(path) for path in artifacts + [checksums]],
                      "manual_installed_ui": "not_run", "development": development}, indent=2))
    return artifacts + [checksums]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path)
    parser.add_argument('--installer', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--development', action='store_true', help='Local test packages, not public release approval')
    args = parser.parse_args()
    package(folder=args.payload, installer=args.installer, release=args.output, development=args.development)


if __name__ == "__main__":
    main()
