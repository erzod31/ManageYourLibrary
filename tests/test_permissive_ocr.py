"""Prevent reintroduction of the legacy OCR dependency/license closure."""
import copy
import hashlib
import io
import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path, PureWindowsPath
from unittest.mock import patch

import ocr_engine
from tools import verify_ocr_payload as verifier
from tools.build_permissive_ocr import extract, normalize_build_paths, source_prefix_flags, verify_extracted_source

ROOT = Path(__file__).resolve().parents[1]


class PermissiveOcrTests(unittest.TestCase):
    def test_windows_compiler_path_map_survives_cmake_script_generation(self):
        flags = source_prefix_flags(PureWindowsPath(r'D:\a\Project Name\dist\ocr'), windows=True)
        self.assertNotIn('\\', flags)
        self.assertEqual(flags, '/experimental:deterministic /pathmap:"D:/a/Project Name/dist/ocr=/usr/src/myl-ocr"')
        self.assertEqual(source_prefix_flags(Path('/tmp/build'), windows=False),
                         '-ffile-prefix-map=/tmp/build=/usr/src/myl-ocr')

    def test_build_receipts_normalize_mixed_windows_separators_and_case(self):
        options = dict(output=Path('C:/Users/SyntheticUser/build'),
                       project=Path('C:/Users/SyntheticUser/project'),
                       home=Path('C:/Users/SyntheticUser'))
        for text in ('-DCMAKE_INSTALL_PREFIX=C:/Users/SyntheticUser/build/prefix',
                     r'-DCMAKE_INSTALL_PREFIX=c:\users\syntheticuser\build\prefix',
                     r'-DCMAKE_INSTALL_PREFIX=C:/USERS\SyntheticUser/build\prefix'):
            normalized = normalize_build_paths(text, **options)
            self.assertTrue(normalized.startswith('-DCMAKE_INSTALL_PREFIX=${BUILD_ROOT}'))
            self.assertNotIn('syntheticuser', normalized.lower())
        self.assertEqual(normalize_build_paths('C:/USERS/SyntheticUser/project/recipe.py', **options),
                         '${PROJECT_ROOT}/recipe.py')
        self.assertEqual(normalize_build_paths('c:/users/syntheticuser/cache', **options),
                         '${USER_PROFILE}/cache')

    def test_posix_receipts_keep_case_and_use_specific_root_before_home(self):
        options = dict(output=Path('/home/synthetic/build'), project=Path('/home/synthetic/project'),
                       home=Path('/home/synthetic'))
        text = '/home/synthetic/build/prefix;/home/synthetic/project/recipe.py;/home/synthetic/cache'
        self.assertEqual(normalize_build_paths(text, **options),
                         '${BUILD_ROOT}/prefix;${PROJECT_ROOT}/recipe.py;${USER_PROFILE}/cache')
        self.assertEqual(normalize_build_paths('/HOME/synthetic/build/prefix', **options),
                         '/HOME/synthetic/build/prefix')

    def test_source_profile_disables_every_legacy_dependency_route(self):
        lock = json.loads((ROOT / 'tools/ocr_source_lock.json').read_text())
        components = {c['id']: c for c in lock['components']}
        self.assertEqual(set(components), {'tesseract', 'leptonica', 'libpng', 'zlib'})
        tess = components['tesseract']['options']
        for key in ('DISABLE_TIFF', 'DISABLE_CURL', 'DISABLE_ARCHIVE', 'GRAPHICS_DISABLED'):
            self.assertEqual(tess[key], 'ON')
        for key in ('BUILD_TRAINING_TOOLS', 'OPENMP_BUILD', 'ENABLE_NATIVE'):
            self.assertEqual(tess[key], 'OFF')
        for codec in ('TIFF', 'JPEG', 'GIF', 'WEBP', 'OPENJPEG'):
            self.assertEqual(components['leptonica']['options']['ENABLE_' + codec], 'OFF')
        self.assertEqual(set(lock['models']), {'eng', 'spa', 'fra', 'nld', 'chi_sim', 'osd'})
        for component in lock['components']:
            self.assertNotIn('GPL', component['license'])
            self.assertNotIn('latest', component['url'])
            self.assertRegex(component['sha256'], r'^[0-9a-f]{64}$')
            self.assertTrue(component['notices'])

    def fixture(self, root):
        (root / 'tools').mkdir()
        payload = root / 'payload'
        payload.mkdir()
        component = {'id': 'example', 'version': '1', 'license': 'Zlib',
                     'sha256': hashlib.sha256(b'source').hexdigest(),
                     'notices': {'LICENSE': hashlib.sha256(b'notice').hexdigest()}}
        lock = {'profile': 'test-profile', 'components': [component], 'models_commit': 'test',
                'models': {'eng': hashlib.sha256(b'model').hexdigest()}}
        (root / 'tools/ocr_source_lock.json').write_text(json.dumps(lock))
        files = {'tesseract': b'fake executable', 'sources/example.tar.gz': b'source',
                 'sources/ocr_source_lock.json': (root / 'tools/ocr_source_lock.json').read_bytes(), 'sources/build_permissive_ocr.py': b'builder',
                 'sources/build-commands.json': b'commands', 'sources/example-CMakeCache.txt': b'cache',
                 'licenses/example/LICENSE': b'notice', 'licenses/example/SOURCE-NOTICES.txt': b'attribution',
                 'licenses/TESSDATA-APACHE-2.0.txt': b'apache', 'tessdata/configs/tsv': b'tsv',
                 'tessdata/configs/txt': b'txt', 'tessdata/eng.traineddata': b'model'}
        for relative, value in files.items():
            path = payload / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(value)
        manifest = {'schema': 1, 'platform': 'linux', 'profile': lock['profile'],
                    'source_lock_sha256': verifier.sha256(root / 'tools/ocr_source_lock.json'),
                    'components': lock['components'], 'models_commit': 'test',
                    'legacy_artifacts_cleared': False,
                    'license_resolution': 'replaced_legacy_stack_no_gpl_lgpl_ocr_libraries',
                    'files': {p: hashlib.sha256(b).hexdigest() for p, b in files.items()}}
        (payload / 'native-ocr-manifest.json').write_text(json.dumps(manifest))
        return payload, manifest

    def test_complete_inventory_is_distinct_from_legacy_clearance(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload, _ = self.fixture(root)
            with patch.object(verifier, 'ROOT', root), patch.object(verifier.sys, 'platform', 'linux'):
                receipt = verifier.validate_payload(payload)
            self.assertFalse(receipt['legacy_artifacts_cleared'])

    def test_payload_rejects_modified_or_missing_notices_sources_models_and_cli(self):
        for relative in ('licenses/example/LICENSE', 'sources/example.tar.gz', 'tessdata/eng.traineddata', 'tesseract'):
            with self.subTest(file=relative), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                payload, _ = self.fixture(root)
                (payload / relative).write_bytes(b'tampered')
                with patch.object(verifier, 'ROOT', root), patch.object(verifier.sys, 'platform', 'linux'):
                    with self.assertRaises(ValueError):
                        verifier.validate_payload(payload)

    def test_added_legacy_dll_is_rejected_even_when_added_to_inventory(self):
        for inventoried in (False, True):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                payload, manifest = self.fixture(root)
                (payload / 'libjbig-0.dll').write_bytes(b'legacy')
                if inventoried:
                    manifest['files']['libjbig-0.dll'] = verifier.sha256(payload / 'libjbig-0.dll')
                    (payload / 'native-ocr-manifest.json').write_text(json.dumps(manifest))
                with patch.object(verifier, 'ROOT', root), patch.object(verifier.sys, 'platform', 'linux'):
                    with self.assertRaises(ValueError):
                        verifier.validate_payload(payload)

    def test_recipe_or_legacy_clearance_tampering_is_rejected(self):
        for change in ('components', 'legacy_artifacts_cleared', 'platform'):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                payload, manifest = self.fixture(root)
                if change == 'components':
                    manifest[change] = copy.deepcopy(manifest[change]) + [{'id': 'jbigkit'}]
                else:
                    manifest[change] = True if change == 'legacy_artifacts_cleared' else 'win32'
                (payload / 'native-ocr-manifest.json').write_text(json.dumps(manifest))
                with patch.object(verifier, 'ROOT', root), patch.object(verifier.sys, 'platform', 'linux'):
                    with self.assertRaises(ValueError):
                        verifier.validate_payload(payload)

    def test_source_archives_reject_traversal_and_links(self):
        for name, link in (('../escape', False), ('source/link', True), ('C:/escape', False), ('source\\escape', False)):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                archive = root / 'bad.tar.gz'
                with tarfile.open(archive, 'w:gz') as out:
                    member = tarfile.TarInfo(name)
                    member.type = tarfile.SYMTYPE if link else tarfile.REGTYPE
                    member.linkname = '/outside' if link else ''
                    out.addfile(member, io.BytesIO())
                with self.assertRaises(ValueError):
                    extract(archive, root / 'extract')
                self.assertFalse((root / 'escape').exists())

    def test_resume_rejects_modified_extracted_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / 'source.tar.gz'
            with tarfile.open(archive, 'w:gz') as out:
                member = tarfile.TarInfo('source/code.c')
                member.size = 1
                out.addfile(member, io.BytesIO(b'x'))
            source = extract(archive, root / 'extract')
            verify_extracted_source(archive, source)
            (source / 'code.c').write_bytes(b'y')
            with self.assertRaises(ValueError):
                verify_extracted_source(archive, source)

    def test_frozen_runtime_never_uses_source_override_or_path_fallback(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(ocr_engine.sys, 'frozen', True, create=True), patch.object(ocr_engine, '_resource_path', return_value=Path(temp) / 'missing'), patch.dict(os.environ, {'MANAGE_YOUR_LIBRARY_OCR_DIR': temp}), patch.object(ocr_engine.shutil, 'which') as which:
            (Path(temp) / 'tesseract.exe').write_bytes(b'external')
            self.assertIsNone(ocr_engine._tesseract_path())
            which.assert_not_called()

    def test_file_helper_converts_non_png_input_without_changing_original(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'fixture.tiff'
            with Image.new('RGB', (20, 20), 'white') as image:
                image.save(path)
            original = path.read_bytes()
            with patch.object(ocr_engine, '_run_tesseract_bytes', return_value=('text', None)) as recognize:
                self.assertEqual(ocr_engine._run_tesseract_file(path, 'eng'), ('text', None))
            self.assertTrue(recognize.call_args.args[0].startswith(b'\x89PNG\r\n\x1a\n'))
            self.assertEqual(path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
