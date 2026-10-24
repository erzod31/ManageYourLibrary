"""Export per-binary license findings and verbatim notices from matched receipts.

No pass/clearance flag is inferred from a library's license family or from the
presence of a text file. Exporting notices alone does not fulfill copyleft source
or combined-work obligations. Existing files are never overwritten.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def json_digest(path):
    value = json.loads(path.read_text(encoding='utf-8'))
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('utf-8'))


def write_review(evidence_path, output, notices_output):
    catalog_path = ROOT / 'tools/ocr_license_catalog.json'
    provenance_path = ROOT / 'docs/validation_data_2026-10-24/windows-ocr-provenance.json'
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    evidence = json.loads(evidence_path.read_text(encoding='utf-8'))
    if evidence['json_fingerprint_encoding'] != 'canonical-json-sorted-ascii-compact':
        raise ValueError('Unsupported JSON fingerprint encoding')
    if evidence['catalog_sha256'] != json_digest(catalog_path) or evidence['provenance_sha256'] != json_digest(provenance_path):
        raise ValueError('The evidence belongs to another catalog or provenance inventory')
    inventory = json.loads(provenance_path.read_text(encoding='utf-8'))
    by_file = {row['file']: row for row in inventory['files']}
    receipts = {row['component']: row for row in evidence['components']}
    if len(receipts) != len(evidence['components']) or set(receipts) != {c['id'] for c in catalog['components']}:
        raise ValueError('Incomplete or duplicate component receipts')
    findings, notices = [], []
    for component in catalog['components']:
        receipt = receipts[component['id']]
        matches = {row['file']: row for row in receipt.get('matching_files', [])}
        if not set(matches).issubset(component['files']):
            raise ValueError('Receipt claims another component\'s binary')
        for filename in component['files']:
            binary = by_file[filename]
            match = matches.get(filename)
            if match and (match['sha256'] != binary['sha256'] or match['expected_sha256'] != binary['sha256']):
                raise ValueError('Binary receipt hash mismatch')
            findings.append({'file': filename, 'sha256': binary['sha256'], 'component': component['id'],
                'reviewed_license': component['license'], 'category': component['category'],
                'upstream_reference': component['upstream'], 'review_note': component['note'],
                'installer_provenance': 'exact_sha256_match' if binary['upstream_installer_matches'] else 'unresolved',
                'package_provenance': 'exact_sha256_match' if match else 'candidate_only',
                'package_version': receipt.get('candidate_package', {}).get('version'),
                'redistribution_status': 'blocked_pending_notices_sources_and_combination_review'})
        if not matches:
            continue
        for notice in receipt.get('notices', []):
            relative = PurePosixPath(notice['package_path']).relative_to('mingw64/share/licenses')
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('Unsafe notice path')
            raw = (evidence_path.parent / component['id'] / 'notices' / relative).read_bytes()
            if sha256(raw) != notice['sha256'] or len(raw) != notice['bytes']:
                raise ValueError('Notice receipt hash mismatch')
            notices.append((Path(component['id']) / relative, raw, notice))
    names = [row['file'] for row in findings]
    if len(names) != len(set(names)) or set(names) != set(by_file):
        raise ValueError('The review must cover each binary exactly once')
    if output.exists():
        raise FileExistsError('Refusing to replace an existing audit report')
    for relative, raw, _ in notices:
        target = notices_output / relative
        if target.exists() and target.read_bytes() != raw:
            raise FileExistsError('Refusing to alter an existing third-party notice')
    report = {'review_date': catalog['review_date'], 'binary_count': len(findings),
        'dll_count': sum(row['file'].endswith('.dll') for row in findings),
        'component_count': len(catalog['components']),
        'json_fingerprint_encoding': evidence['json_fingerprint_encoding'],
        'exact_installer_matches': sum(row['installer_provenance'] == 'exact_sha256_match' for row in findings),
        'exact_package_matches': sum(row['package_provenance'] == 'exact_sha256_match' for row in findings),
        'catalog_sha256': evidence['catalog_sha256'], 'package_evidence_sha256': sha256(evidence_path.read_bytes()),
        'provenance_sha256': evidence['provenance_sha256'],
        'redistribution_review': 'not_complete', 'source_obligations_fulfilled': False,
        'native_security_review': 'not_complete', 'findings': sorted(findings, key=lambda row: row['file']),
        'package_receipts': evidence['components'],
        'verbatim_notice_files': [{'path': path.as_posix(), **notice} for path, raw, notice in notices]}
    notices_output.mkdir(parents=True, exist_ok=True)
    for relative, raw, _ in notices:
        target = notices_output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(raw)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('binary_count', 'dll_count', 'component_count',
                      'exact_package_matches', 'redistribution_review')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--notices-output', type=Path, required=True)
    args = parser.parse_args()
    write_review(args.evidence, args.output, args.notices_output)
