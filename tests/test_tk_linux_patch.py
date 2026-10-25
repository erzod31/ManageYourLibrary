"""Fail-closed Linux native patch recipe/provenance, without GUI or readers."""
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import tk_linux_patch as native


class LinuxNativePatchTests(unittest.TestCase):
    def fixture(self, directory):
        tree = Path(directory)
        unix = tree / 'unix'
        unix.mkdir()
        raw = b'upstream provider input\n'
        (unix / 'tkUnixAccessibility.c').write_bytes(raw)
        return tree, {'tkUnixAccessibility.c': hashlib.sha256(raw).hexdigest()}

    def test_exact_context_required(self):
        for source in ('missing', 'same same'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                native.replace_once(source, 'same', 'repaired')

    def test_function_replacement_preserves_neighbors(self):
        source = ('static void example(int x)\n{\n    if (x) { x++; }\n}\n'
                  'static void neighbor(void);\n')
        result = native.replace_function(source, 'example', '    return;')
        self.assertEqual(result, 'static void example(int x)\n{\n    return;\n}\nstatic void neighbor(void);\n')

    def test_forward_declaration_is_not_replaced(self):
        source = 'static void example(int x);\nstatic void other(void)\n{\n    return;\n}\n'
        with self.assertRaisesRegex(ValueError, 'Missing pinned Linux Tk function'):
            native.replace_function(source, 'example', 'return;')

    def test_remove_event_function_keeps_other_functions_and_rejects_declaration(self):
        source = 'static void Atk_Event_Check(void *x, int flags)\n{\n    return;\n}\nstatic int next(void);\n'
        self.assertEqual(native.remove_function(source, 'Atk_Event_Check'), '\nstatic int next(void);\n')
        with self.assertRaisesRegex(ValueError, 'Missing pinned Linux Tk event function'):
            native.remove_function('static void Atk_Event_Check(void *x, int flags);\n', 'Atk_Event_Check')

    def test_unknown_upstream_hash_does_not_change_source(self):
        with tempfile.TemporaryDirectory() as directory:
            tree, _ = self.fixture(directory)
            before = (tree / 'unix/tkUnixAccessibility.c').read_bytes()
            with self.assertRaisesRegex(ValueError, 'Unrecognized native Linux source'):
                native.apply_linux_patch(tree)
            self.assertEqual((tree / 'unix/tkUnixAccessibility.c').read_bytes(), before)
            self.assertFalse((tree / native.RECEIPT).exists())

    def test_context_mismatch_does_not_change_hash_accepted_source(self):
        with tempfile.TemporaryDirectory() as directory:
            tree, hashes = self.fixture(directory)
            before = (tree / 'unix/tkUnixAccessibility.c').read_bytes()
            with patch.object(native, 'INPUT_HASHES', hashes), self.assertRaises(ValueError):
                native.apply_linux_patch(tree)
            self.assertEqual((tree / 'unix/tkUnixAccessibility.c').read_bytes(), before)

    def test_receipt_binds_exact_inputs_outputs_and_recipe_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            tree, hashes = self.fixture(directory)
            with patch.object(native, 'INPUT_HASHES', hashes), patch.object(native, 'repair_provider', return_value='patched\n'):
                result = native.apply_linux_patch(tree)
                self.assertEqual(result['patch_id'], native.PATCH_ID)
                self.assertEqual(result['input_hashes'], hashes)
                self.assertEqual(set(result['output_hashes']), {'tkUnixAccessibility.c', *native.HELPERS.values()})
                for name, digest in result['output_hashes'].items():
                    self.assertEqual(hashlib.sha256((tree / 'unix' / name).read_bytes()).hexdigest(), digest)
                self.assertEqual(native.apply_linux_patch(tree), result)

    def test_modified_provider_or_copied_helper_rejected(self):
        for name in ('tkUnixAccessibility.c', *native.HELPERS.values()):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                tree, hashes = self.fixture(directory)
                with patch.object(native, 'INPUT_HASHES', hashes), patch.object(native, 'repair_provider', return_value='patched\n'):
                    native.apply_linux_patch(tree)
                    (tree / 'unix' / name).write_bytes(b'tampered')
                    with self.assertRaisesRegex(ValueError, 'Modified patched native Linux source'):
                        native.apply_linux_patch(tree)

    def test_modified_recipe_or_input_provenance_rejected(self):
        for key, value in (('patcher_sha256', '0' * 64), ('input_hashes', {}), ('output_hashes', {})):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                tree, hashes = self.fixture(directory)
                with patch.object(native, 'INPUT_HASHES', hashes), patch.object(native, 'repair_provider', return_value='patched\n'):
                    native.apply_linux_patch(tree)
                    receipt = tree / native.RECEIPT
                    content = json.loads(receipt.read_text())
                    content[key] = value
                    receipt.write_text(json.dumps(content))
                    with self.assertRaisesRegex(ValueError, 'Different native Linux accessibility patch'):
                        native.apply_linux_patch(tree)

    def test_changed_repository_helper_rejected_on_resume(self):
        for changed in native.HELPERS:
            with self.subTest(helper=changed), tempfile.TemporaryDirectory() as directory:
                tree, hashes = self.fixture(directory)
                with patch.object(native, 'INPUT_HASHES', hashes), patch.object(native, 'repair_provider', return_value='patched\n'):
                    native.apply_linux_patch(tree)
                    alternate = tree / 'alternative-helper'
                    alternate.mkdir()
                    for original in native.HELPERS:
                        (alternate / original).write_bytes((native.NATIVE / original).read_bytes())
                    (alternate / changed).write_bytes(b'changed recipe helper')
                    with patch.object(native, 'NATIVE', alternate), self.assertRaisesRegex(ValueError, 'Different native Linux accessibility helper'):
                        native.apply_linux_patch(tree)

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Real ATK native helper requires Linux development libraries')
    def test_real_atk_window_focus_index_and_live_client_after_destroy(self):
        compiler = shutil.which('cc')
        pkg_config = shutil.which('pkg-config')
        if not compiler or not pkg_config:
            if os.environ.get('GITHUB_ACTIONS') == 'true':
                self.fail('Linux CI must provide cc and pkg-config for the native provider contract')
            self.skipTest('Native helper requires cc and pkg-config')
        flags = subprocess.run([pkg_config, '--cflags', '--libs', 'atk'], capture_output=True, text=True, check=False)
        if flags.returncode:
            if os.environ.get('GITHUB_ACTIONS') == 'true':
                self.fail('Linux CI must provide real ATK development headers and library')
            self.skipTest('Native helper requires ATK development headers and library')
        source = native.NATIVE / 'test_tkUnixA11yWindow.c'
        with tempfile.TemporaryDirectory(prefix='myl_atk_contract_') as directory:
            binary = Path(directory) / 'atk-window-contract'
            compilation = subprocess.run([compiler, '-std=c11', '-Wall', '-Wextra', '-Werror', str(source),
                                          '-o', str(binary), *shlex.split(flags.stdout)],
                                         capture_output=True, text=True, timeout=30, check=False)
            self.assertEqual(compilation.returncode, 0, compilation.stderr[-8000:])
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10,
                                    env={**os.environ, 'G_DEBUG': 'fatal-warnings'}, check=False)
            self.assertEqual(result.returncode, 0, result.stderr[-8000:])
            self.assertIn('ATK window contract: passed', result.stdout)

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Real anonymous Tk/ATK windows require Linux')
    def test_two_real_panedwindow_anonymous_proxies_register_without_glib_warnings(self):
        import tkinter as tk
        if tk.TkVersion != 9.1:
            self.skipTest('Pinned Tk 9.1 runtime is exercised by the native-build job')
        # Each classic PanedWindow allocates an unnamed proxy in Tk's native
        # childList, which recursive ATK registration visits even when hidden.
        script = '''import tkinter as tk
root = tk.Tk()
try:
    first = tk.PanedWindow(root, name="pane_\u00e9\u4e66")
    second = tk.PanedWindow(root, name="pane_second")
    first.pack()
    second.pack()
    root.update()
    root.tk.call("::tk::accessible::add_acc_object", ".")
    root.update()
    assert first.winfo_exists() and second.winfo_exists()
    assert root.tk.call("package", "present", "Tk") == "9.1.0"
    print("anonymous PanedWindow ATK registration: passed")
finally:
    root.destroy()
'''
        result = subprocess.run([sys.executable, '-B', '-c', script], capture_output=True,
                                text=True, timeout=15, check=False,
                                env={**os.environ, 'G_DEBUG': 'fatal-warnings'})
        self.assertEqual(result.returncode, 0, result.stderr[-8000:])
        self.assertNotIn('GLib-CRITICAL', result.stderr)
        self.assertIn('anonymous PanedWindow ATK registration: passed', result.stdout)


if __name__ == '__main__':
    unittest.main()
