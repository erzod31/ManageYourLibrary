import argparse
import hashlib
import importlib.metadata
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.verify_ocr_payload import validate_payload as validate_ocr_payload


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def git_value(*args):
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def source_tree_fingerprint():
    """Hash build-relevant source/config files, including untracked files."""
    output = git_value("ls-files", "--cached", "--others", "--exclude-standard")
    if output == "unknown":
        return {"sha256": "unknown", "files": 0}
    allowed_suffixes = {
        ".bat", ".ico", ".iss", ".json", ".lock", ".md", ".ps1",
        ".py", ".sh", ".spec", ".txt", ".yaml", ".yml",
        ".dll", ".exe", ".traineddata", ".svg", ".png", ".webp", ".c", ".h",
    }
    digest = hashlib.sha256()
    count = 0
    for relative in sorted(line for line in output.splitlines() if line.strip()):
        path = ROOT / relative
        if not path.is_file() or (
            path.suffix.lower() not in allowed_suffixes
            and relative not in {"VERSION", ".gitignore", "LICENSE"}
        ):
            continue
        # Derived evidence is completed after building; it is not a build input.
        if re.fullmatch(r"docs/windows_[^/]+_checksums\.md", relative.replace("\\", "/")):
            continue
        if any(part in {"build", "dist", "__pycache__", ".ruff_cache"} for part in path.parts):
            continue
        encoded_path = relative.replace("\\", "/").encode("utf-8")
        digest.update(len(encoded_path).to_bytes(4, "big"))
        digest.update(encoded_path)
        digest.update(bytes.fromhex(sha256(path)))
        count += 1
    return {"sha256": digest.hexdigest().upper(), "files": count}


def validate_threading_evidence(artifact, report_path, platform, version):
    """Bind frozen mainloop evidence to final EXE, extension and source receipt."""
    from tools.verify_tkinter_threading import validate_report
    artifact, report_path = Path(artifact), Path(report_path)
    platform_name = {'windows-x64': 'win32', 'linux': 'linux', 'macos': 'darwin'}.get(platform)
    if platform_name is None:
        raise ValueError('Unsupported threading evidence platform')
    payload = artifact.parents[2] if platform == 'macos' else artifact.parent
    suffix = '.pyd' if platform == 'windows-x64' else '.so'
    bridges = {path.resolve() for path in payload.rglob('_tkinter*' + suffix) if path.is_file()}
    if len(bridges) != 1 or not next(iter(bridges)).is_relative_to(payload.resolve()):
        raise ValueError('Frozen threading evidence needs one application-local _tkinter extension')
    bridge_hash = sha256(bridges.pop()).lower()
    contract_hash = sha256(ROOT / 'tools/verify_tkinter_threading.py').lower()
    relative = Path('licenses/tcltk/myl-tkinter-tcl9-repair')
    roots = [payload / '_internal'] if platform != 'macos' else [payload / 'Contents/Resources', payload / 'Contents/Frameworks']
    contracts = {(root / relative / 'verify_tkinter_threading.py').resolve() for root in roots
                 if (root / relative / 'verify_tkinter_threading.py').is_file()}
    if len(contracts) != 1:
        raise ValueError('Missing or ambiguous packaged bridge contract source')
    contract = contracts.pop()
    if not contract.is_relative_to(payload.resolve()) or sha256(contract).lower() != contract_hash:
        raise ValueError('Packaged bridge contract source differs from current source')
    builder = json.loads((contract.parent / 'threading-contract.json').read_text(encoding='utf-8'))
    # Ad-hoc signing changes the macOS extension after the builder contract;
    # the frozen contract must bind the final signed extension separately.
    validate_report(builder, expected_bridge_sha256=bridge_hash if platform != 'macos' else None,
                    expected_contract_sha256=contract_hash, expected_platform=platform_name)
    report = json.loads(report_path.read_text(encoding='utf-8'))
    return validate_report(report, expected_bridge_sha256=bridge_hash, expected_contract_sha256=contract_hash,
                           expected_platform=platform_name, expected_version=version, expected_frozen=True,
                           expected_executable_sha256=sha256(artifact).lower())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "artifact",
        nargs="?",
        type=Path,
        default=ROOT / "dist" / "windows" / "ManageYourLibrary" / "ManageYourLibrary.exe",
    )
    parser.add_argument("--platform", default=sys.platform)
    parser.add_argument("--validated-release-gates", action="store_true")
    parser.add_argument("--validated-runtime", action="store_true")
    parser.add_argument("--validated-first-use", action="store_true")
    parser.add_argument('--validated-windows-accessibility', action='store_true')
    parser.add_argument('--validated-tkinter-threading', action='store_true')
    parser.add_argument('--tkinter-threading-report', type=Path)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    artifact = args.artifact.resolve()
    if not artifact.exists():
        raise SystemExit(f"Artifact not found: {artifact}")
    packages = {}
    for name in ("pypdf", "pypdfium2", "Pillow", "ftfy", "pyinstaller"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "missing"
    ocr_directory = artifact.parent / '_internal/tesseract'
    if args.platform in {'linux', 'macos'}:
        # Native signing can relocate/sign Mach-O data inside .app. Retain the
        # validated source payload receipt separately from final package hashes.
        ocr_directory = ROOT / 'platforms' / args.platform / 'tesseract'
    ocr = None
    if (ocr_directory / 'native-ocr-manifest.json').is_file():
        ocr = validate_ocr_payload(ocr_directory)
    native_origins = None
    wheel_notices = None
    python_notices = None
    threading_contract = None
    if args.validated_tkinter_threading:
        threading_contract = validate_threading_evidence(
            artifact, args.tkinter_threading_report or artifact.parent / 'tkinter-threading-self-test.json',
            args.platform, (ROOT / 'VERSION').read_text(encoding='utf-8').strip())
    if args.platform == 'windows-x64':
        from tools.verify_wheel_redistribution import verify_windows_payload
        from tools.windows_dependency_policy import verify_payload
        native_origins = verify_payload(artifact.parent)
        wheel_notices = verify_windows_payload(artifact.parent)
        from tools.verify_python_license_payload import verify_windows_payload
        python_notices = verify_windows_payload(artifact.parent)
    manifest = {
        "artifact": artifact.relative_to(ROOT).as_posix() if artifact.is_relative_to(ROOT) else artifact.name,
        "size": artifact.stat().st_size,
        "sha256": sha256(artifact),
        "version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        "git_commit": git_value("rev-parse", "HEAD"),
        "git_status": git_value("status", "--short"),
        "source_tree": source_tree_fingerprint(),
        "python": sys.version,
        "platform": args.platform,
        "packages": packages,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ocr_source_payload": ocr,
        'windows_native_origins': native_origins,
        'windows_wheel_notices': wheel_notices,
        'windows_python_notices': python_notices,
        'tkinter_threading_self_test': threading_contract,
        "validation": {
            "automated_tests": "passed" if args.validated_release_gates else "not_recorded",
            "source_smoke": "passed" if args.validated_release_gates else "not_recorded",
            "catalog_performance_gate": "passed" if args.validated_release_gates else "not_recorded",
            "frozen_smoke": "passed" if args.validated_release_gates else "not_recorded",
            "runtime_self_test": "passed" if args.validated_runtime else "not_recorded",
            "first_use_self_test": "passed" if args.validated_first_use else "not_recorded",
            'windows_accessibility_self_tests': 'passed' if args.validated_windows_accessibility else 'not_recorded',
            'tkinter_threading_self_test': 'passed' if threading_contract else 'not_recorded',
            "manual_installed_ui": "not_run",
            "code_signing": "not_performed",
            "redistribution_review": "not_complete",
            "ocr_libraries_profile": "passed" if ocr else "not_recorded",
        },
    }
    output = artifact.parent / "build-manifest.json"
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
