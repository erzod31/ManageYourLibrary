"""Block native public releases until all three complete license reviews pass.

Actions build/test artifacts are not a claim of redistribution clearance.
This gate never approves a review; it only checks previously recorded approvals.
"""
import argparse
import json
from pathlib import Path

EXPECTED = {('linux', 'x64'), ('macos', 'arm64'), ('macos', 'x64')}


def check(directory):
    found = set()
    for path in sorted(Path(directory).glob('*-manifest.json')):
        if path.name.endswith('-ocr-manifest.json'):
            continue
        manifest = json.loads(path.read_text(encoding='utf-8'))
        target = (manifest.get('platform'), manifest.get('architecture'))
        if target not in EXPECTED or target in found:
            raise ValueError('Unexpected or repeated native license review target')
        validation = manifest.get('validation', {})
        if validation.get('redistribution_review') != 'passed':
            raise ValueError('Public release blocked: complete redistribution review is pending for ' + str(target))
        if (validation.get('ocr_libraries_profile') != 'passed'
                or manifest.get('ocr_source_payload', {}).get('resolution')
                != 'replaced_legacy_stack_no_gpl_lgpl_ocr_libraries'):
            raise ValueError('Public release blocked: controlled OCR review is missing')
        found.add(target)
    if found != EXPECTED:
        raise ValueError('Public release blocked: all three platform reviews are required')
    return len(found)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    print('Previously approved native redistribution reviews: ' + str(check(args.directory)))
