import json
import sys
from pathlib import Path


def _version():
    try:
        return (Path(__file__).resolve().parent / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "0.5.0"


def smoke_test():
    import library_core
    import ocr_engine
    from core.operation_plans import OperationPlanStore
    from core.catalog_store import CatalogStore

    checks = {
        "version": _version(),
        "library_core": bool(library_core.EXTENSIONES_LIBROS),
        "ocr_engine": callable(ocr_engine.extraer_texto_documento_ocr),
        "operation_plans": OperationPlanStore.__name__,
        "catalog_model": CatalogStore.__name__,
        "identity_policy": library_core.ANALYSIS_CACHE_VERSION,
    }
    print(json.dumps(checks, ensure_ascii=False, sort_keys=True))
    return 0 if all((checks["library_core"], checks["ocr_engine"])) else 1


def cli(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--first-use-self-test" in argv:
        from tools.first_use_self_test import run_and_record

        position = argv.index("--first-use-self-test")
        if position + 1 >= len(argv):
            raise ValueError("--first-use-self-test requires an output JSON path")
        return run_and_record(Path(argv[position + 1]), version=_version())
    if "--runtime-self-test" in argv:
        from tools.runtime_self_test import run_and_record

        position = argv.index("--runtime-self-test")
        if position + 1 >= len(argv):
            raise ValueError("--runtime-self-test requires an output JSON path")
        return run_and_record(Path(argv[position + 1]), version=_version())
    if "--version" in argv:
        print(_version())
        return 0
    if "--smoke-test" in argv or "--diagnostics" in argv:
        return smoke_test()
    from library_app import main

    main()
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
