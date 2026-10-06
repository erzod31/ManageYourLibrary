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
        ".dll", ".exe", ".traineddata", ".svg", ".png", ".webp",
    }
    digest = hashlib.sha256()
    count = 0
    for relative in sorted(line for line in output.splitlines() if line.strip()):
        path = ROOT / relative
        if not path.is_file() or (
            path.suffix.lower() not in allowed_suffixes
            and relative not in {"VERSION", ".gitignore"}
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
        "validation": {
            "automated_tests": "passed" if args.validated_release_gates else "not_recorded",
            "source_smoke": "passed" if args.validated_release_gates else "not_recorded",
            "catalog_performance_gate": "passed" if args.validated_release_gates else "not_recorded",
            "frozen_smoke": "passed" if args.validated_release_gates else "not_recorded",
            "runtime_self_test": "passed" if args.validated_runtime else "not_recorded",
            "first_use_self_test": "passed" if args.validated_first_use else "not_recorded",
            "manual_installed_ui": "not_run",
            "code_signing": "not_performed",
        },
    }
    output = artifact.parent / "build-manifest.json"
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
