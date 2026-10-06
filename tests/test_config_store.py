import tempfile
import unittest
from pathlib import Path

from core import config_store, index_store


class ConfigStoreTests(unittest.TestCase):
    def test_operation_config_is_bounded_and_invalid_theme_is_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            index_store.guardar_json(
                path,
                {
                    "operation": {
                        "ocr_max_pages": 999,
                        "offline_mode": True,
                        "theme": "unknown",
                    }
                },
            )

            self.assertEqual(
                config_store.load_operation_config(path),
                {"ocr_max_pages": 200, "offline_mode": True, "theme": "system"},
            )

    def test_corrupt_page_value_falls_back_without_losing_other_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            index_store.guardar_json(
                path,
                {
                    "operation": {
                        "ocr_max_pages": "not-a-number",
                        "offline_mode": True,
                        "theme": "dark",
                    }
                },
            )

            self.assertEqual(
                config_store.load_operation_config(path),
                {"ocr_max_pages": 12, "offline_mode": True, "theme": "dark"},
            )

    def test_saving_operation_config_preserves_unrelated_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            index_store.guardar_json(
                path,
                {
                    "library": "old-library",
                    "ai_local": {"enabled": True, "model_id": "kept"},
                    "custom": {"keep": True},
                },
            )

            cleaned = config_store.save_operation_config(
                path,
                {"ocr_max_pages": 0, "offline_mode": False, "theme": "LIGHT"},
                library=None,
                language="es",
            )
            saved = index_store.cargar_json(path, {})

            self.assertEqual(cleaned, {"ocr_max_pages": 1, "offline_mode": False, "theme": "light"})
            self.assertEqual(saved["library"], "old-library")
            self.assertEqual(saved["ai_local"], {"enabled": True, "model_id": "kept"})
            self.assertEqual(saved["custom"], {"keep": True})

    def test_saving_library_config_preserves_operation_and_ai_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            index_store.guardar_json(
                path,
                {
                    "operation": {"ocr_max_pages": 20, "offline_mode": False, "theme": "dark"},
                    "ai_local": {"enabled": False},
                },
            )

            config_store.save_library_config(path, library="C:/Books", language="es")
            saved = index_store.cargar_json(path, {})

            self.assertEqual(saved["library"], "C:/Books")
            self.assertEqual(saved["language"], "es")
            self.assertEqual(saved["operation"]["theme"], "dark")
            self.assertEqual(saved["ai_local"], {"enabled": False})


if __name__ == "__main__":
    unittest.main()
