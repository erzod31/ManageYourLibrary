"""Minimal CPython Tcl 9 thread detection backport on a separate source copy.

The pinned download remains unchanged for reproducible builds and resume.
CPython's upstream fix uses the always-threaded Tcl 9 contract instead of the
removed tcl_platform(threaded) variable. Python and busywaitinterval are intact.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

PATCH_ID = 'myl-cpython312-tcl9-threaded-1'
INPUT_SHA256 = 'c484afe880de65c628f5376adf0be413eae2f0d339d5ef5f33365c14ba59eca3'
SOURCE_URL = 'https://raw.githubusercontent.com/python/cpython/v3.12.10/Modules/_tkinter.c'
FIX_REFERENCE = ('https://github.com/python/cpython/blob/'
                 '4a5a7b9f6d528c9be272d876ed7ca620f0e40038/Modules/_tkinter.c')
TCL_CONTRACT = 'https://core.tcl-lang.org/tcl/wiki?name=Migrating+scripts+to+Tcl+9'
OUTPUT = 'myl_tkinter.c'
RECEIPT = 'myl-tkinter-tcl9-patch.json'
BEFORE = '''    v->threaded = Tcl_GetVar2Ex(v->interp, "tcl_platform", "threaded",
                                TCL_GLOBAL_ONLY) != NULL;'''
AFTER = '''#if TCL_MAJOR_VERSION >= 9
    v->threaded = 1;
#else
''' + BEFORE + '\n#endif'


def repair_source(source):
    if source.count(BEFORE) != 1:
        raise ValueError('Pinned CPython thread detector context mismatch')
    return source.replace(BEFORE, AFTER, 1)


def apply_bridge_patch(modules):
    modules = Path(modules)
    original = modules / '_tkinter.c'
    raw = original.read_bytes()
    if hashlib.sha256(raw).hexdigest() != INPUT_SHA256:
        raise ValueError('Unrecognized CPython _tkinter source')
    output, receipt = modules / OUTPUT, modules / RECEIPT
    recipe = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    repaired = repair_source(raw.decode('utf-8')).encode('utf-8')
    result = {'patch_id': PATCH_ID, 'input_sha256': INPUT_SHA256,
              'output_sha256': hashlib.sha256(repaired).hexdigest(), 'patcher_sha256': recipe,
              'python_version': '3.12.10', 'source_url': SOURCE_URL,
              'fix_reference': FIX_REFERENCE, 'tcl_contract': TCL_CONTRACT,
              'change': 'Tcl 9 uses the threaded mainloop and owner-thread marshalling; '
                        'Tcl 8 detection and busywaitinterval are unchanged.',
              'license': 'CPython PSF and historical licenses; see bundled CPYTHON-LICENSE'}
    if receipt.exists():
        if (json.loads(receipt.read_text(encoding='utf-8')) != result
                or output.read_bytes() != repaired):
            raise ValueError('Stale or modified CPython Tcl 9 bridge repair')
        return result
    if output.exists():
        raise FileExistsError('Unrecorded CPython bridge output already exists')
    output.write_bytes(repaired)
    receipt.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result
