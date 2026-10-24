"""Compare OCR bytes to the upstream installer and identify exact model blobs.

Reads PE import tables and metadata without loading DLLs or running the installer.
Matching a publisher's binary establishes provenance, not license clearance of
that publisher's transitive dependencies. Reports contain no local profile paths.
"""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

UPSTREAM_INSTALLER = ('https://github.com/tesseract-ocr/tesseract/releases/download/'
                      '5.5.0/tesseract-ocr-w64-setup-5.5.0.20241111.exe')


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def api(path):
    request = urllib.request.Request('https://api.github.com/' + path,
                                     headers={'User-Agent': 'ManageYourLibrary-provenance-audit'})
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.load(response)


def model_sources(runtime):
    models = {}
    for path in (runtime / 'tessdata').glob('*.traineddata'):
        content = path.read_bytes()
        models[path.name] = {'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content),
            'git_blob_sha1': hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest(),
            'matches': []}
    for repository in ('tessdata_fast', 'tessdata_best', 'tessdata'):
        commit = api('repos/tesseract-ocr/' + repository + '/commits/main')['sha']
        tree = api('repos/tesseract-ocr/' + repository + '/git/trees/' + commit + '?recursive=1')
        if tree.get('truncated'):
            raise RuntimeError('Model tree was truncated')
        for entry in tree['tree']:
            model = models.get(entry['path'])
            if model and entry['sha'] == model['git_blob_sha1']:
                url = f'https://raw.githubusercontent.com/tesseract-ocr/{repository}/{commit}/{entry["path"]}'
                # Confirm with SHA-256 as well, rather than relying on Git SHA-1.
                with urllib.request.urlopen(url, timeout=60) as response:
                    if hashlib.sha256(response.read()).hexdigest() != model['sha256']:
                        raise RuntimeError('Model SHA-256 differs from the matching Git blob')
                model['matches'].append({'repository': 'tesseract-ocr/' + repository,
                    'commit': commit, 'url': url,
                    'license_url': f'https://github.com/tesseract-ocr/{repository}/blob/{commit}/LICENSE'})
    return models


def audit(runtime, reference, installer):
    import pefile
    references = {}
    for path in reference.rglob('*'):
        if path.is_file():
            references.setdefault(path.name.lower(), []).append(path)
    files = []
    bundled = {p.name.lower() for p in runtime.iterdir() if p.suffix.lower() in {'.dll', '.exe'}}
    for path in sorted(runtime.iterdir()):
        if path.suffix.lower() not in {'.dll', '.exe'}:
            continue
        binary = pefile.PE(str(path), fast_load=False)
        try:
            imports = sorted({entry.dll.decode('ascii').lower() for entry in getattr(binary, 'DIRECTORY_ENTRY_IMPORT', [])})
            version = {}
            for group in getattr(binary, 'FileInfo', []):
                for entry in group:
                    for table in getattr(entry, 'StringTable', []):
                        for key, value in table.entries.items():
                            if key in {b'FileVersion', b'ProductVersion', b'ProductName', b'LegalCopyright'}:
                                version[key.decode()] = value.decode('utf-8', errors='replace')[:500]
            digest = sha256(path)
            matches = [p.relative_to(reference).as_posix() for p in references.get(path.name.lower(), []) if sha256(p) == digest]
            files.append({'file': path.name, 'sha256': digest, 'bytes': path.stat().st_size,
                'upstream_installer_matches': matches, 'metadata': version,
                'bundled_imports': [name for name in imports if name in bundled],
                'other_imports': [name for name in imports if name not in bundled],
                'individual_redistribution_review': 'not_complete'})
        finally:
            binary.close()
    return {'scope': 'Exact binary/model provenance; no inference that the installer clears every DLL license',
        'upstream_installer': {'url': UPSTREAM_INSTALLER, 'sha256': sha256(installer), 'bytes': installer.stat().st_size},
        'binary_count': len(files), 'exact_upstream_matches': sum(bool(row['upstream_installer_matches']) for row in files),
        'files': files, 'models': model_sources(runtime),
        'redistribution_review': 'not_complete', 'installer_executed': False,
        'native_security_audit': 'not_complete'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--installer', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.runtime, args.reference, args.installer)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('binary_count', 'exact_upstream_matches', 'redistribution_review')}))
    print('Identified models:', sum(bool(row['matches']) for row in result['models'].values()))
