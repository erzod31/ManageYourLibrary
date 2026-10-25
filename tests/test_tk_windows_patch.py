"""Fail-closed native patching and COM adapter generation without GUI access."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import tk_windows_patch as native


class NativePatchTests(unittest.TestCase):
    def test_exact_context_required(self):
        for value in ('missing', 'same same'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                native.replace_once(value, 'same', 'replacement')

    def test_function_replacement_preserves_signature_and_neighbors(self):
        source = 'void example(int value)\n{\n    if (value) { value++; }\n}\nvoid neighbor(void);\n'
        updated = native.replace_function(source, 'example', '    return;')
        self.assertEqual(updated, 'void example(int value)\n{\nreturn;\n}\nvoid neighbor(void);\n')

    def test_missing_function_fails(self):
        with self.assertRaises(ValueError):
            native.replace_function('void other(void);', 'missing', 'return;')

    def test_all_com_adapters_use_owner_thread_and_unique_status_slot(self):
        source = ''.join('static HRESULT STDMETHODCALLTYPE\nTkRootAccessible_' + name
                         + '(IAccessible *self)\n{\n    return S_OK;\n}\n' for name in native.METHODS)
        updated = native.marshal_methods(source)
        self.assertEqual(updated.count('return MylDispatch(MylInvoke_'), len(native.METHODS))
        self.assertEqual(updated.count('HRESULT status;'), len(native.METHODS))
        self.assertNotIn('HRESULT result;', updated)
        self.assertEqual(updated.count('Tcl_SaveInterpState'), len(native.METHODS))
        self.assertEqual(updated.count('Tcl_RestoreInterpState'), len(native.METHODS))

    def test_missing_com_method_fails_before_build(self):
        with self.assertRaises(ValueError):
            native.marshal_methods('')

    def fixtures(self, directory):
        tree = Path(directory)
        win = tree / 'win'
        win.mkdir()
        source = b'provider input'
        wm = b'    switch (message) {\n    case WM_KILLFOCUS:\n    case WM_ERASEBKGND:'
        (win / 'tkWinAccessibility.c').write_bytes(source)
        (win / 'tkWinWm.c').write_bytes(wm)
        hashes = {'tkWinAccessibility.c': hashlib.sha256(source).hexdigest(),
                  'tkWinWm.c': hashlib.sha256(wm).hexdigest()}
        return tree, hashes

    def test_unknown_source_is_not_modified(self):
        with tempfile.TemporaryDirectory() as directory:
            tree, _hashes = self.fixtures(directory)
            with self.assertRaisesRegex(ValueError, 'Unrecognized native source'):
                native.apply_windows_patch(tree)
            self.assertEqual((tree / 'win/tkWinAccessibility.c').read_bytes(), b'provider input')
            self.assertFalse((tree / 'myl-accessibility-patch.json').exists())

    def test_native_receipt_binds_inputs_outputs_and_recipe(self):
        with tempfile.TemporaryDirectory() as directory:
            tree, hashes = self.fixtures(directory)
            with patch.object(native, 'INPUT_HASHES', hashes), patch.object(native, 'repair_provider', return_value='patched\n'):
                result = native.apply_windows_patch(tree)
                self.assertEqual(result['patch_id'], native.PATCH_ID)
                self.assertEqual(result['input_hashes'], hashes)
                self.assertEqual(len(result['output_hashes']), 6)
                for name, expected in result['output_hashes'].items():
                    self.assertEqual(hashlib.sha256((tree / 'win' / name).read_bytes()).hexdigest(), expected)
                self.assertEqual(native.apply_windows_patch(tree), result)

    def test_modified_patched_source_is_rejected_on_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            tree, hashes = self.fixtures(directory)
            with patch.object(native, 'INPUT_HASHES', hashes), patch.object(native, 'repair_provider', return_value='patched\n'):
                native.apply_windows_patch(tree)
                (tree / 'win/tkWinAccessibility.c').write_text('tampered', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'Modified patched native source'):
                    native.apply_windows_patch(tree)

    def test_different_patch_recipe_is_rejected_on_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            tree, hashes = self.fixtures(directory)
            with patch.object(native, 'INPUT_HASHES', hashes), patch.object(native, 'repair_provider', return_value='patched\n'):
                native.apply_windows_patch(tree)
                receipt = tree / 'myl-accessibility-patch.json'
                content = json.loads(receipt.read_text(encoding='utf-8'))
                content['patcher_sha256'] = '0' * 64
                receipt.write_text(json.dumps(content), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'Different native accessibility patch'):
                    native.apply_windows_patch(tree)


if __name__ == '__main__':
    unittest.main()
