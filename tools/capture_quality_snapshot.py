import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))


SUPPORTED_EXTENSIONS = {
    ".azw",
    ".azw3",
    ".bmp",
    ".epub",
    ".jpeg",
    ".jpg",
    ".mobi",
    ".pdf",
    ".png",
    ".tif",
    ".tiff",
    ".txt",
    ".webp",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _offline_consultar_web(libro, callback=None, datos=None, **kwargs):
    if callback:
        callback("Offline quality snapshot: external providers disabled")
    return datos or {}, []


def _track_ocr_calls():
    import ocr_engine

    calls = []
    originals = {}
    for name in ("extraer_texto_documento_ocr", "extraer_texto_imagen_bytes_ocr"):
        original = getattr(ocr_engine, name)
        originals[name] = original

        def tracked(*args, __name=name, __original=original, **kwargs):
            calls.append(__name)
            return __original(*args, **kwargs)

        setattr(ocr_engine, name, tracked)
    return calls, originals


def _restore_ocr_calls(originals):
    import ocr_engine

    for name, original in originals.items():
        setattr(ocr_engine, name, original)


def _identity_record(path: Path, root: Path, result: dict, ocr_calls: list[str]) -> dict:
    confidence = float(result.get("confianza_global", result.get("confianza", 0)) or 0)
    found = bool(result.get("encontrado"))
    status = str(result.get("estado_analisis", "") or "")
    if not status:
        status = "OCR_OK" if found and ocr_calls else "ACCEPTED" if found else "NEEDS_REVIEW"
    return {
        "relative_path": _relative(path, root),
        "format": path.suffix.lower(),
        "title": str(result.get("titulo", "") or ""),
        "author": str(result.get("autor", "") or ""),
        "year": str(result.get("anio", "") or ""),
        "isbn": str(result.get("isbn", "") or ""),
        "confidence": round(confidence, 3),
        "status": status,
        "primary_method": str(result.get("metodo", result.get("metodo_identificacion", "")) or ""),
        "ocr_used": bool(ocr_calls),
        "sent_to_review": not found,
        "found": found,
        "action": str(result.get("accion_recomendada", "") or ""),
        "error": str(result.get("error", "") or ""),
    }


def capture_deep_snapshot(paths: list[Path], root: Path) -> tuple[list[dict], float]:
    import library_core as core

    original_consultar_web = core.consultar_web
    core.consultar_web = _offline_consultar_web
    started = time.perf_counter()
    records = []
    try:
        for path in paths:
            calls, originals = _track_ocr_calls()
            try:
                result = core.resolver_identidad_libro(path, solo_analizar=True)
            finally:
                _restore_ocr_calls(originals)
            records.append(_identity_record(path, root, result, calls))
    finally:
        core.consultar_web = original_consultar_web
    return records, time.perf_counter() - started


def _fast_record(path: Path, root: Path, result: dict) -> dict:
    identity = dict(result.get("identity_result", {}) or {})
    return {
        "relative_path": _relative(path, root),
        "format": str(result.get("format", path.suffix.lower()) or ""),
        "title": str(result.get("title", "") or ""),
        "author": str(result.get("author", "") or ""),
        "year": str(result.get("year", "") or ""),
        "isbn": str(result.get("isbn", "") or ""),
        "confidence": round(float(result.get("confidence", 0) or 0), 3),
        "status": str(result.get("status", "") or ""),
        "primary_method": str(result.get("primary_method", "") or ""),
        "ocr_used": False,
        "sent_to_review": result.get("status") in {"NEEDS_REVIEW", "ERROR"},
        "found": bool(identity.get("encontrado")),
        "action": str(identity.get("accion_recomendada", "") or ""),
        "error": str(result.get("error", "") or ""),
    }


def capture_fast_snapshot(paths: list[Path], root: Path, *, parallel=False) -> tuple[list[dict], float]:
    import library_core as core

    if not hasattr(core, "analizar_archivo_rapido"):
        raise RuntimeError("Fast quality snapshots require the performance pipeline branch.")
    started = time.perf_counter()
    if parallel:
        results = core.analizar_archivos_rapido_en_paralelo(paths)
    else:
        results = [core.analizar_archivo_rapido(path) for path in paths]
    return [
        _fast_record(path, root, result)
        for path, result in zip(paths, results)
    ], time.perf_counter() - started


def duplicate_snapshot(paths: list[Path], root: Path) -> dict:
    groups = {}
    for path in paths:
        groups.setdefault(_sha256(path), []).append(_relative(path, root))
    exact_groups = [
        sorted(items)
        for items in groups.values()
        if len(items) > 1
    ]
    exact_groups.sort()
    return {
        "exact_duplicate_groups": exact_groups,
        "exact_duplicate_group_count": len(exact_groups),
        "exact_duplicate_file_count": sum(len(group) for group in exact_groups),
    }


def capture(root: Path, mode: str, label: str) -> dict:
    root = root.resolve()
    paths = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    if mode == "deep":
        records, elapsed = capture_deep_snapshot(paths, root)
    elif mode == "fast-sequential":
        records, elapsed = capture_fast_snapshot(paths, root, parallel=False)
    elif mode == "fast-parallel":
        records, elapsed = capture_fast_snapshot(paths, root, parallel=True)
    else:
        raise ValueError(f"Unknown snapshot mode: {mode}")
    return {
        "label": label,
        "mode": mode,
        "root": str(root),
        "files_total": len(paths),
        "elapsed_seconds": round(elapsed, 4),
        "status_counts": dict(sorted(Counter(item["status"] for item in records).items())),
        "duplicates": duplicate_snapshot(paths, root),
        "records": records,
    }


def main():
    parser = argparse.ArgumentParser(description="Capture a deterministic local/offline quality snapshot.")
    parser.add_argument("--root", required=True, help="Controlled fixture folder to scan.")
    parser.add_argument("--output", required=True, help="JSON output path.")
    parser.add_argument("--label", required=True, help="Human-readable snapshot label.")
    parser.add_argument("--mode", choices=("deep", "fast-sequential", "fast-parallel"), default="deep")
    args = parser.parse_args()

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    snapshot = capture(Path(args.root), args.mode, args.label)
    output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "label": snapshot["label"],
        "mode": snapshot["mode"],
        "files_total": snapshot["files_total"],
        "elapsed_seconds": snapshot["elapsed_seconds"],
        "status_counts": snapshot["status_counts"],
        "exact_duplicate_groups": snapshot["duplicates"]["exact_duplicate_group_count"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
