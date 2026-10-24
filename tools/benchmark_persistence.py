"""Measure durable edits, not only warmed-up search. Synthetic profiles only."""
import argparse
import json
import math
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run(sizes, repetitions):
    with tempfile.TemporaryDirectory(prefix='myl_persistence_') as directory:
        from core import config_store
        with patch.object(config_store, 'app_data_dir', return_value=Path(directory)):
            import library_core as core
        from tools.benchmark_catalog import synthetic_catalog
        results = []
        for size in sizes:
            state = Path(directory) / str(size)
            state.mkdir()
            with patch.multiple(core, INDICE_JSON=state/'index.json', CATALOG_DB=state/'catalog.sqlite3'):
                index = {'archivos': synthetic_catalog(size)}
                start = time.perf_counter()
                core.guardar_indice(index)
                initial_ms = (time.perf_counter() - start) * 1000
                timings = []
                for count in range(repetitions + 3):
                    path = index['archivos'][(size - 1) * (count % 3) // 2]['ruta']
                    start = time.perf_counter()
                    index = core.aplicar_correccion_manual_indice(path, {'favorite': bool(count % 2)}, index)
                    elapsed = (time.perf_counter() - start) * 1000
                    if count >= 3:
                        timings.append(elapsed)
                result = {'size': size, 'samples': repetitions, 'initial_save_ms': round(initial_ms, 2),
                          'edit_median_ms': round(statistics.median(timings), 2),
                          'edit_p95_ms': round(sorted(timings)[max(0, math.ceil(repetitions * .95) - 1)], 2),
                          'files': core.catalog_store().stats()['present_files']}
                results.append(result)
                print(json.dumps(result), flush=True)
        return {'python': platform.python_version(), 'results': results}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--sizes', nargs='+', type=int, default=[1000, 10000, 50000])
    parser.add_argument('--repetitions', type=int, default=100)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = run(args.sizes, args.repetitions)
    if args.output:
        args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    raise SystemExit(0 if all(row['files'] == row['size'] and row['edit_p95_ms'] < 200 for row in result['results']) else 1)
