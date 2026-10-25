"""Bounded, read-only AT-SPI diagnostics for the synthetic CI fixture.

This is API evidence only. It never substitutes for Orca presentation, changes
desktop settings, or attaches to applications other than the requested PID.
The controller runs it with a separate process timeout before fixture cleanup.
"""
from __future__ import annotations

import argparse
import json


def inspect_fixture(pid, desktop, state_name, *, maximum=250, depth_limit=10, progress=None):
    if type(pid) is not int or pid <= 0:
        raise ValueError('A positive owned fixture PID is required')
    report = {'scope': 'atspi_api_diagnostic_not_reader_certification', 'applications': [],
              'status': 'in_progress', 'visited': 0, 'truncated': False, 'errors': [],
              'descendant_traversal_enabled': depth_limit > 0}
    if progress:
        progress(report)
    for app in desktop:
        try:
            if app.get_process_id() != pid:
                continue
            entry = {'name': (app.name or '')[:160], 'windows': [], 'focused': []}
            report['applications'].append(entry)
            if progress:
                progress(report)
            pending = [(app[index], 0) for index in range(min(app.childCount, maximum))]
            report['truncated'] = app.childCount > maximum
            while pending and report['visited'] < maximum:
                node, depth = pending.pop(0)
                report['visited'] += 1
                states = sorted(state_name(value) for value in node.getState().getStates())
                row = {'name': (node.name or '')[:160], 'role': node.getRoleName(),
                       'index_in_parent': node.getIndexInParent(), 'states': states}
                if depth == 0:
                    entry['windows'].append(row)
                if 'focused' in [value.lower().removeprefix('state_') for value in states]:
                    entry['focused'].append(row)
                count = node.childCount
                if depth < depth_limit:
                    limit = max(0, min(count, maximum - report['visited'] - len(pending)))
                    pending.extend((node[index], depth + 1) for index in range(limit))
                    report['truncated'] = report['truncated'] or limit < count
                elif count:
                    report['truncated'] = True
                if progress:
                    progress(report)
            report['truncated'] = report['truncated'] or bool(pending)
        except Exception as exc:
            report['errors'].append(type(exc).__name__)
    report['status'] = 'complete'
    if progress:
        progress(report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--windows-only', action='store_true',
                        help='Inspect up to eight application windows without walking all descendants')
    args = parser.parse_args()
    import pyatspi
    def emit(report):
        print(json.dumps(report), flush=True)
    inspect_fixture(args.pid, pyatspi.Registry.getDesktop(0), pyatspi.stateToString,
                    maximum=8 if args.windows_only else 250,
                    depth_limit=0 if args.windows_only else 10, progress=emit)


if __name__ == '__main__':
    main()
