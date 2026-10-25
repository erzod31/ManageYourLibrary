"""Block native public releases until all three complete license reviews pass.

Actions build/test artifacts are not a claim of redistribution clearance.
This gate never approves a review; it only checks previously recorded approvals.
"""
import argparse
import json
import hashlib
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
        if target[0] == 'linux':
            source = manifest.get('linux_os_library_evidence', {})
            name = source.get('archive', '')
            if (not isinstance(name, str) or Path(name).name != name or not name.endswith('-license-sources.tar')
                    or source.get('source_asset_required_with_release') is not True):
                raise ValueError('Public release blocked: complete Linux source-delivery evidence is required')
            archive = Path(directory) / name
            if archive.is_symlink() or not archive.is_file():
                raise ValueError('Public release blocked: Linux source asset is missing')
            with archive.open('rb') as stream:
                actual = hashlib.file_digest(stream, 'sha256').hexdigest()
            if actual != source.get('sha256'):
                raise ValueError('Public release blocked: Linux source asset hash differs')
        found.add(target)
    if found != EXPECTED:
        raise ValueError('Public release blocked: all three platform reviews are required')
    return len(found)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    print('Previously approved native redistribution reviews: ' + str(check(args.directory)))
