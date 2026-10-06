import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import library_core
from core import file_identity


class FileIdentityTests(unittest.TestCase):
    def test_complete_hash_matches_sha256_and_compatibility_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "book.epub"
            payload = b"book-payload" * 100
            path.write_bytes(payload)

            expected = hashlib.sha256(payload).hexdigest()
            self.assertEqual(file_identity.sha256_file(path, block_size=17), expected)
            self.assertEqual(library_core.calcular_hash(path, bloque=17), expected)

    def test_partial_signature_detects_tail_and_size_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "book.pdf"
            path.write_bytes(b"A" * 128 + b"B" * 128)
            original = file_identity.partial_file_signature(path, block_size=64)

            path.write_bytes(b"A" * 128 + b"C" * 128)
            changed_tail = file_identity.partial_file_signature(path, block_size=64)
            self.assertNotEqual(original, changed_tail)

            path.write_bytes(b"A" * 128 + b"C" * 129)
            changed_size = file_identity.partial_file_signature(path, block_size=64)
            self.assertNotEqual(changed_tail, changed_size)

    def test_live_comparison_revalidates_current_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first.epub"
            second = Path(tmp) / "second.epub"
            first.write_bytes(b"same")
            second.write_bytes(b"same")
            self.assertTrue(file_identity.live_files_identical(first, second))

            second.write_bytes(b"else")
            self.assertFalse(file_identity.live_files_identical(first, second))

    def test_live_comparison_rejects_file_changed_during_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first.epub"
            second = Path(tmp) / "second.epub"
            first.write_bytes(b"same")
            second.write_bytes(b"same")
            original_hash = file_identity.sha256_file
            initial_stat = first.stat()
            calls = 0

            def mutate_after_first_hash(path, block_size=1024 * 1024):
                nonlocal calls
                result = original_hash(path, block_size)
                calls += 1
                if calls == 1:
                    first.write_bytes(b"new!")
                    # Equal-size rapid writes may share a timestamp on Windows.
                    # Make the signature change deterministic, without sleeps
                    # or weakening the rejection expected from the safeguard.
                    os.utime(first, ns=(initial_stat.st_atime_ns,
                                        initial_stat.st_mtime_ns + 2_000_000_000))
                    self.assertNotEqual(first.stat().st_mtime_ns,
                                        initial_stat.st_mtime_ns)
                return result

            with mock.patch.object(file_identity, "sha256_file", side_effect=mutate_after_first_hash):
                self.assertFalse(file_identity.live_files_identical(first, second))

    def test_validated_hash_raises_when_file_changes_mid_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "book.epub"
            path.write_bytes(b"before")
            original_hash = file_identity.sha256_file

            def mutate_after_hash(target, block_size=1024 * 1024):
                result = original_hash(target, block_size)
                path.write_bytes(b"after-content")
                return result

            with (
                mock.patch.object(file_identity, "sha256_file", side_effect=mutate_after_hash),
                self.assertRaises(file_identity.FileChangedDuringReadError),
            ):
                file_identity.validated_sha256_file(path)

    def test_live_comparison_is_false_for_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            present = Path(tmp) / "present.epub"
            present.write_bytes(b"book")
            self.assertFalse(file_identity.live_files_identical(present, Path(tmp) / "missing.epub"))


if __name__ == "__main__":
    unittest.main()
