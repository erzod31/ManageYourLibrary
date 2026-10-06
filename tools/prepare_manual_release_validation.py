import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = REPO_ROOT / "manual_release_validation"
MARKER_NAME = ".manageyourlibrary_manual_validation.json"
VERSION = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def safe_validation_root(value: str | Path) -> Path:
    root = Path(value)
    if not root.is_absolute():
        root = REPO_ROOT / root
    root = root.resolve()
    if root == REPO_ROOT or not _is_relative_to(root, REPO_ROOT):
        raise ValueError("The validation folder must stay inside the repository root.")
    return root


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_unicode_epub(path: Path):
    container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""
    content_opf = """<?xml version="1.0" encoding="UTF-8"?>
<package version="2.0" xmlns="http://www.idpf.org/2007/opf"
         unique-identifier="book-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>El niño y 三体</dc:title>
    <dc:creator>Álvaro Núñez</dc:creator>
    <dc:date>2026</dc:date>
    <dc:language>es</dc:language>
    <dc:identifier id="book-id">manual-validation-unicode-fixture</dc:identifier>
  </metadata>
  <manifest>
    <item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="chapter"/>
  </spine>
</package>
"""
    chapter = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>El niño y 三体</title></head>
  <body><h1>El niño y 三体</h1><p>Fixture sintético para validación manual.</p></body>
</html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", container_xml)
        archive.writestr("OEBPS/content.opf", content_opf)
        archive.writestr("OEBPS/chapter.xhtml", chapter)


def _write_ocr_fixtures(folder: Path):
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise RuntimeError("Pillow is required to create the synthetic OCR fixtures.") from exc

    folder.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1600, 420), "white")
    draw = ImageDraw.Draw(image)
    draw.text((90, 130), "MANAGE YOUR LIBRARY OCR TEST 2026", fill="black")
    image.save(folder / "ocr-fixture.png")
    image.save(folder / "scanned-fixture.pdf", "PDF", resolution=150.0)


def _powershell_quote(value: Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _write_launcher(root: Path):
    exe = REPO_ROOT / "dist" / "windows" / "ManageYourLibrary" / "ManageYourLibrary.exe"
    script = f"""$env:APPDATA = {_powershell_quote(root / "appdata")}
$env:LOCALAPPDATA = {_powershell_quote(root / "localappdata")}
$env:PATH = 'C:\\Windows\\System32;C:\\Windows'
Start-Process -FilePath {_powershell_quote(exe)}
"""
    _write_text(root / "launch_frozen_validation.ps1", script)


def _fixture_record(root: Path, path: Path, purpose: str):
    return {
        "path": path.relative_to(root).as_posix(),
        "purpose": purpose,
        "sha256": sha256(path),
        "size": path.stat().st_size,
    }


def prepare_validation(root: Path, reset=False) -> dict:
    root = safe_validation_root(root)
    marker = root / MARKER_NAME
    if root.exists() and any(root.iterdir()):
        if not reset:
            raise RuntimeError(f"{root} already contains files. Use --reset only for a folder created by this tool.")
        if not marker.is_file():
            raise RuntimeError(f"Refusing to reset an unmarked folder: {root}")
        shutil.rmtree(root)

    folders = (
        "appdata",
        "localappdata",
        "input/add_books",
        "input/exact_duplicate",
        "input/metadata_search",
        "library",
        "review",
        "ocr",
        "expected",
        "results",
    )
    for relative in folders:
        (root / relative).mkdir(parents=True, exist_ok=True)

    low_confidence = root / "input" / "add_books" / "Libro sintético ñ 三体.txt"
    duplicate = root / "input" / "exact_duplicate" / "Libro sintético duplicado ñ 三体.txt"
    metadata_search = root / "input" / "metadata_search" / "Metadatos Unicode ñ 三体.epub"
    _write_text(low_confidence, "Synthetic fixture without reliable bibliographic metadata.\n")
    shutil.copyfile(low_confidence, duplicate)
    _write_unicode_epub(metadata_search)
    _write_ocr_fixtures(root / "ocr")
    _write_launcher(root)

    fixture_specs = (
        (low_confidence, "Add books low-confidence fixture"),
        (duplicate, "Exact duplicate of the Add books fixture"),
        (metadata_search, "Search metadata Unicode rename-in-place fixture"),
        (root / "ocr" / "ocr-fixture.png", "Local OCR image fixture"),
        (root / "ocr" / "scanned-fixture.pdf", "Frozen OCR and PDFium fixture"),
    )
    manifest = {
        "tool": "Manage Your Library manual release validation",
        "version": VERSION,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "root": str(root),
        "fixtures": [_fixture_record(root, path, purpose) for path, purpose in fixture_specs],
    }
    marker.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (root / "expected" / "fixture_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def _print_instructions(root: Path):
    python = Path(sys.executable)
    print()
    print("Manual release-validation fixtures are ready.")
    print(f"Validation root: {root}")
    print()
    print("1. Start the frozen EXE from PowerShell:")
    print(f"   powershell -ExecutionPolicy Bypass -File \"{root / 'launch_frozen_validation.ps1'}\"")
    print(f"2. Select this temporary library in the app: {root / 'library'}")
    print("3. Follow docs/manual_click_validation_form_windows.md.")
    print("4. Generate a local filesystem report afterward:")
    print(f'   \"{python}\" tools/check_manual_release_results.py --root \"{root}\"')
    print()
    print("The helper never selects, reads, or modifies a personal library.")


def main():
    parser = argparse.ArgumentParser(description="Prepare synthetic fixtures for a frozen Windows EXE click-through.")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Validation folder inside the repository.")
    parser.add_argument("--reset", action="store_true", help="Reset a previously marked validation folder.")
    args = parser.parse_args()

    root = safe_validation_root(args.root)
    prepare_validation(root, reset=args.reset)
    _print_instructions(root)


if __name__ == "__main__":
    main()
