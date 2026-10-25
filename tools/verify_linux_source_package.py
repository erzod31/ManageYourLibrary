"""Verify the Linux source-asset writer on a disposable application copy.

Dedicated Linux GitHub CI only: MYL_ISOLATED_SOURCE_CI=1. No application,
upstream archive, reader, audio backend, or other subprocess is executed.
This independent QA artifact never clears app/Orca/publication gates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.collect_linux_license_evidence import relative_name
from tools.package_linux_license_evidence import (
    MAX_FILES,
    REPORT,
    _validate,
    prepare,
    sha256,
)
from tools.verify_linux_library_replacement import payload_inventory

SCOPE = 'source_asset_writer_qa_not_app_release_or_global_license_approval'
REVIEW = 'source-package-review.json'
BLOCK = 1024 * 1024


def inventory_digest(inventory):
    return hashlib.sha256(json.dumps(inventory, sort_keys=True).encode('utf-8')).hexdigest()


def validate_tar(archive, expected_files, hashes):
    """Read every member as bytes; never extract or open nested source archives."""
    seen = set()
    with tarfile.open(archive, mode='r:') as tar:
        for member in tar:
            if len(seen) >= MAX_FILES + 1:
                raise ValueError('Oversized source asset member inventory')
            name = member.name
            relative_name(name)
            if (name in seen or name not in expected_files or not member.isfile()
                    or member.uid != 0 or member.gid != 0 or member.uname or member.gname
                    or member.mode != 0o644 or member.mtime != 0):
                raise ValueError('Unexpected source asset member or personal metadata')
            if member.size != expected_files[name].stat().st_size:
                raise ValueError('Source asset member size mismatch')
            stream = tar.extractfile(member)
            if stream is None:
                raise ValueError('Unreadable source asset member')
            hasher = hashlib.sha256()
            count = 0
            with stream:
                while data := stream.read(BLOCK):
                    count += len(data)
                    hasher.update(data)
            if count != member.size or hasher.hexdigest() != hashes[name]:
                raise ValueError('Source asset member SHA-256 mismatch')
            seen.add(name)
    if seen != set(expected_files):
        raise ValueError('Incomplete source asset contents')
    return len(seen)


def output_boundary(payload, evidence, output):
    if output.exists() or output.is_symlink():
        raise FileExistsError('Source review directory must be NEW; existing evidence is never overwritten')
    resolved = output.resolve()
    if resolved.is_relative_to(payload.resolve()) or resolved.is_relative_to(evidence.resolve()):
        raise ValueError('Source review output must remain outside original payload and evidence')


def run_checks(payload: Path, evidence: Path, output: Path, label: str):
    report = {'schema': 1, 'passed': False, 'status': 'not_run', 'scope': SCOPE,
              'publishable_release': False, 'checks': {}, 'application_executed': False,
              'reader_started': False, 'audio_started': False,
              'remaining_review': ['normal app/Orca/extracted-release gates remain independent',
                                   'library replacement and package-specific licenses require separate review',
                                   'this does not establish global redistribution or patent approval']}
    if sys.platform != 'linux':
        report['reason'] = 'linux_only'
        return report
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('MYL_ISOLATED_SOURCE_CI') != '1':
        report['reason'] = 'requires_dedicated_isolated_source_ci'
        return report
    payload, evidence, output = Path(payload), Path(evidence), Path(output)
    if payload.is_symlink() or not payload.is_dir() or evidence.is_symlink() or not evidence.is_dir():
        raise ValueError('Payload and evidence must be ordinary directories')
    payload, evidence = payload.resolve(), evidence.resolve()
    output_boundary(payload, evidence, output)
    before = None
    phase = 'input_inventory'
    checks = report['checks']
    try:
        before = payload_inventory(payload)
        report['original_payload_inventory_sha256'] = inventory_digest(before)
        report['original_payload_entries'] = len(before)
        phase = 'validate_collected_evidence'
        collector, files, hashes = _validate(evidence)
        report['collector_report_sha256'] = hashes[REPORT]
        report['source_families'] = len(collector['source_archives'])
        report['unowned_origins'] = len(collector.get('unowned_binary_origins', []))
        checks['complete_collector_inventory_verified'] = True
        with tempfile.TemporaryDirectory(prefix='myl_linux_source_writer_ci_') as temporary:
            copy = Path(temporary).resolve() / 'app'
            phase = 'copy_application'
            shutil.copytree(payload, copy, symlinks=True)
            if payload_inventory(copy) != before:
                raise ValueError('Disposable application copy differs before writer execution')
            checks['complete_disposable_copy'] = True
            phase = 'prepare_source_asset'
            receipt = prepare(copy, evidence, output, label)
            archive = output / receipt['archive']
            relative_name(receipt['archive'])
            if (archive.parent.resolve() != output.resolve() or archive.is_symlink()
                    or receipt['archive'] != receipt['name'] or sha256(archive) != receipt['sha256']):
                raise ValueError('Source asset identity/hash differs from writer receipt')
            checks['source_tar_sha256_matches_receipt'] = True
            phase = 'read_source_tar'
            report['verified_tar_members'] = validate_tar(archive, files, hashes)
            checks['source_tar_complete_exact_bytes'] = True
            target = copy / '_internal/licenses/linux-system'
            receipt_path = target / 'source-asset.json'
            if receipt_path.is_symlink() or json.loads(receipt_path.read_text(encoding='utf-8')) != receipt:
                raise ValueError('Application source reference differs from writer receipt')
            if (receipt.get('scope') != 'verified_evidence_delivery_not_global_license_approval'
                    or receipt.get('source_asset_required_with_release') is not True
                    or receipt.get('evidence_report_sha256') != hashes[REPORT]):
                raise ValueError('Writer receipt has an unsupported scope or collector identity')
            checks['application_reference_matches_asset'] = True
            phase = 'verify_small_application_notices'
            notice_hashes = {name: checksum for name, checksum in hashes.items()
                             if name.startswith(('copyright/', 'common-licenses/'))}
            expected_additions = {'_internal/licenses/linux-system/' + name: {'sha256': checksum}
                                  for name, checksum in notice_hashes.items()}
            expected_additions['_internal/licenses/linux-system/source-asset.json'] = {'sha256': sha256(receipt_path)}
            if payload_inventory(copy) != {**before, **expected_additions} or receipt.get('application_notices_sha256') != notice_hashes:
                raise ValueError('Writer added unexpected files or changed application bytes')
            checks['only_copyright_common_licenses_and_reference_added'] = True
            report['source_asset'] = {'name': archive.name, 'sha256': receipt['sha256'], 'bytes': archive.stat().st_size}
            report['writer_receipt'] = receipt
        report['status'] = 'passed'
    except (OSError, ValueError, RuntimeError, TypeError, KeyError, tarfile.TarError) as exc:
        report['status'] = 'failed'
        report['reason'] = type(exc).__name__
        report['failed_stage'] = phase
    finally:
        if before is not None:
            try:
                after = payload_inventory(payload)
                report['original_payload_after_sha256'] = inventory_digest(after)
                checks['original_payload_unchanged'] = after == before
            except (OSError, ValueError):
                checks['original_payload_unchanged'] = False
        if report['status'] == 'passed' and not all(checks.values()):
            report['status'] = 'failed'
    report['passed'] = report['status'] == 'passed' and all(checks.values())
    return report


def run_and_record(payload, evidence, output, label):
    report = run_checks(payload, evidence, output, label)
    if report['status'] != 'not_run':
        output = Path(output)
        output.mkdir(parents=True, exist_ok=True)
        with (output / REVIEW).open('x', encoding='utf-8') as stream:
            json.dump(report, stream, indent=2)
            stream.write('\n')
    print(json.dumps({'status': report['status'], 'scope': SCOPE, 'publishable_release': False,
                      'failed_stage': report.get('failed_stage')}))
    return 0 if report['passed'] else 2 if report['status'] == 'not_run' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', required=True, type=Path)
    parser.add_argument('--evidence', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--label', required=True)
    args = parser.parse_args()
    raise SystemExit(run_and_record(args.payload, args.evidence, args.output, args.label))
