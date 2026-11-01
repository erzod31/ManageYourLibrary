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
    if argv == ["--ocr-worker"]:
        from core.ocr_runtime import worker_main

        return worker_main()
    if "--update-self-test" in argv:
        from tools.update_runtime_self_test import run_and_record

        position=argv.index("--update-self-test")
        if position+1>=len(argv):
            raise ValueError("--update-self-test requires an output JSON path")
        return run_and_record(Path(argv[position+1]),version=_version())
    if "--apply-update" in argv:
        if not getattr(sys, "frozen", False) or sys.platform == "win32":
            raise ValueError("The POSIX update helper requires the installed native application")
        from core.config_store import app_data_dir
        from core.update_apply import apply_posix_plan

        position = argv.index("--apply-update")
        if position + 1 >= len(argv):
            raise ValueError("--apply-update requires a private confirmed plan")
        plan=json.loads(Path(argv[position+1]).read_text(encoding="utf-8"))
        actual_root=Path(sys.executable).resolve().parents[2] if sys.platform=="darwin" else Path(sys.executable).resolve().parent
        if Path(plan["installRoot"]).resolve()!=actual_root:
            raise ValueError("The update plan does not belong to this installed application")
        apply_posix_plan(Path(argv[position + 1]), app_data_dir() / "updates")
        return 0
    if "--mobile-self-test" in argv:
        from tools.mobile_runtime_self_test import run_and_record

        position = argv.index("--mobile-self-test")
        if position + 1 >= len(argv):
            raise ValueError("--mobile-self-test requires an output JSON path")
        return run_and_record(Path(argv[position + 1]), version=_version())
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
