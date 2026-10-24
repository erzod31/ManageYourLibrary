"""Versioned synthetic evaluation. No network, personal catalog or model tuning."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CORPUS = ROOT / 'tests' / 'fixtures' / 'identity_corpus_v1.json'


def evidence_for(case):
    from book_identity_evidence import make_evidence
    variant = case['variant']
    sources = ['embedded', 'catalog_a', 'catalog_b']
    if variant == 'filename':
        sources = ['filename']
    elif variant == 'repeat':
        sources = ['catalog_a'] * 30
    elif variant == 'weak_ocr':
        sources = ['cover_ocr']
    evidence = []
    for source in sources:
        for field, value in [('title', case['title']), ('author', case['author']), ('year', '2026')]:
            if variant == 'title_only' and field != 'title':
                continue
            item = make_evidence(field, value, source, 45, quality=.3 if variant == 'weak_ocr' else 1)
            if item:
                evidence.append(item)
    contradictions = {'language_conflict': ('language', 'eng', 'spa'),
                      'volume_conflict': ('volume', '1', '2'),
                      'edition_conflict': ('edition', 'First', 'Revised'),
                      'language_alias': ('language', 'eng', 'en')}
    if variant in contradictions:
        field, first, second = contradictions[variant]
        evidence.extend([make_evidence(field, first, 'embedded', 80), make_evidence(field, second, 'catalog_a', 80)])
    return list(reversed(evidence)) if variant == 'reordered' else evidence


def edit_distance(first, second):
    row = list(range(len(second) + 1))
    for position, char in enumerate(first, 1):
        following = [position]
        for column, other in enumerate(second, 1):
            following.append(min(following[-1] + 1, row[column] + 1, row[column - 1] + (char != other)))
        row = following
    return row[-1]


def evaluate(split='evaluation', with_ocr=False):
    from book_identity_scorer import score_identity, AUTO_RENAME
    corpus = json.loads(CORPUS.read_text(encoding='utf-8'))
    rows = []
    for case in corpus['cases']:
        if case['split'] != split:
            continue
        started = time.perf_counter()
        result = score_identity(evidence_for(case))
        automatic = result['decision'] == AUTO_RENAME
        correct = result['title'] == case['title'] and result['author'] == case['author']
        rows.append({'id': case['id'], 'decision': result['decision'], 'confidence': result['confidence_percent'],
                     'fields_match': correct, 'automatic': automatic, 'safe_auto_label': case['safe_auto'],
                     'unsafe_decision': automatic and (not case['safe_auto'] or not correct),
                     'elapsed_ms': round((time.perf_counter() - started) * 1000, 3)})
    automatic = sum(row['automatic'] for row in rows)
    unsafe = sum(row['unsafe_decision'] for row in rows)
    report = {'corpus_sha256': hashlib.sha256(CORPUS.read_bytes()).hexdigest(), 'schema': 1,
              'split': split, 'license': corpus['license'], 'scope': corpus['scope'],
              'cases': rows, 'count': len(rows), 'automatic_count': automatic,
              'automatic_precision': (automatic - unsafe) / automatic if automatic else None,
              'automatic_coverage': automatic / len(rows) if rows else 0,
              'unsafe_decisions': unsafe, 'actual_file_operations': 0,
              'field_accuracy': sum(row['fields_match'] for row in rows) / len(rows)}
    if with_ocr:
        from PIL import Image, ImageDraw, ImageFont
        from core.reader_worker import run_reader
        results = []
        with tempfile.TemporaryDirectory(prefix='myl_corpus_') as directory:
            for case in corpus['ocr']:
                if case['split'] != split:
                    continue
                image = Image.new('RGB', (1500, 260), 'white')
                ImageDraw.Draw(image).text((60, 90), case['text'], fill='black', font=ImageFont.load_default(size=60))
                image = image.rotate(case['rotation'], expand=False, fillcolor='white')
                path = Path(directory) / (case['id'] + '.png')
                image.save(path)
                started = time.perf_counter()
                result = run_reader('ocr_file', {'path': str(path), 'kwargs': {'max_paginas': 1}}, timeout=180)
                recognized = ' '.join(result.get('texto', '').upper().split())
                results.append({'id': case['id'], 'character_error_rate': edit_distance(case['text'], recognized) / len(case['text']),
                                'exact': recognized == case['text'], 'error': result.get('error'),
                                'elapsed_ms': round((time.perf_counter() - started) * 1000, 2)})
        report['ocr'] = results
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=['tuning', 'evaluation'], default='evaluation')
    parser.add_argument('--ocr', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='myl_corpus_profile_') as directory:
        os.environ['MANAGE_YOUR_LIBRARY_PROFILE'] = str(Path(directory) / 'profile')
        os.environ['MANAGE_YOUR_LIBRARY_OFFLINE'] = '1'
        report = evaluate(args.split, args.ocr)
    encoded = json.dumps(report, indent=2, ensure_ascii=True)
    print(encoded)
    if args.output:
        args.output.write_text(encoded + '\n', encoding='utf-8')
    return int(report['unsafe_decisions'] != 0)


if __name__ == '__main__':
    raise SystemExit(main())
