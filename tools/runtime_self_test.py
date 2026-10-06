"""Bounded local runtime checks; never load a personal library or configuration."""
from __future__ import annotations

import io
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REQUIRED_LANGUAGES = ("eng", "spa", "fra", "nld", "chi_sim")
FIXTURE_TEXT = "LIBRARY TEST 2026"


def run_checks(version: str) -> dict:
    report = {"version": version, "frozen": bool(getattr(sys, "frozen", False)),
              "created_at": datetime.now(timezone.utc).isoformat(), "checks": {}}
    checks = report["checks"]

    def check(name, callback):
        try:
            callback()
            checks[name] = "passed"
        except Exception as exc:
            checks[name] = f"failed: {type(exc).__name__}: {exc}"

    def pillow():
        from PIL import Image, ImageDraw, ImageFont
        image = Image.new("RGB", (1200, 220), "white")
        draw = ImageDraw.Draw(image)
        draw.text((45, 70), FIXTURE_TEXT, fill="black", font=ImageFont.load_default(size=64))
        return image

    def tk_runtime():
        import tkinter as tk
        root = tk.Tk()
        try:
            root.withdraw()
            root.update_idletasks()
        finally:
            root.destroy()

    def bundled_languages():
        import ocr_engine
        base = ocr_engine._resource_path("tesseract")
        executable = base / ("tesseract.exe" if sys.platform == "win32" else "tesseract")
        if not executable.is_file() or ocr_engine._tesseract_path() != executable:
            raise RuntimeError("Expected the bundled OCR executable, not a PATH fallback")
        for language in REQUIRED_LANGUAGES:
            if not (base / "tessdata" / f"{language}.traineddata").is_file():
                raise RuntimeError(f"Missing OCR language: {language}")

    def recognize(image):
        import ocr_engine
        with io.BytesIO() as stream:
            image.save(stream, format="PNG")
            text, error = ocr_engine._run_tesseract_bytes(stream.getvalue(), "eng", timeout=20)
        if error or FIXTURE_TEXT not in text.upper():
            raise RuntimeError(error or f"Synthetic OCR text mismatch: {text!r}")

    def image_ocr():
        with pillow() as image:
            recognize(image)

    def pdf_ocr():
        import pypdfium2 as pdfium
        with pillow() as image, io.BytesIO() as stream:
            image.save(stream, format="PDF", resolution=96)
            with pdfium.PdfDocument(stream.getvalue()) as document:
                page = document[0]
                bitmap = None
                rendered = None
                try:
                    bitmap = page.render(scale=2)
                    rendered = bitmap.to_pil()
                    recognize(rendered)
                finally:
                    if rendered is not None:
                        rendered.close()
                    if bitmap is not None:
                        bitmap.close()
                    page.close()

    # The synthetic checks write no application state and use no network.
    with tempfile.TemporaryDirectory(prefix="myl_runtime_"):
        check("tk_init", tk_runtime)
        check("bundled_languages", bundled_languages)
        check("image_ocr", image_ocr)
        check("pdfium_ocr", pdf_ocr)
    report["passed"] = all(value == "passed" for value in checks.values())
    report["manual_installed_ui"] = "not_run"
    return report


def run_and_record(output: Path, *, version: str) -> int:
    report = run_checks(version)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1
