import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import library_app
from core import config_store, index_store
from tools import first_use_self_test
from ui.workspace import TEXT


class FirstUseTests(unittest.TestCase):
    def test_missing_state_uses_defaults_without_creating_a_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "new-profile"
            self.assertEqual(config_store.load_operation_config(state / "config.json"),
                             config_store.DEFAULT_OPERATION_CONFIG)
            self.assertEqual(index_store.cargar_indice(state / "library_index.json")["archivos"], [])
            self.assertFalse(state.exists())

    def test_unconfigured_library_field_is_empty(self):
        app = object.__new__(library_app.App)
        app.biblioteca_var = Mock()
        with patch.object(library_app, "biblioteca_configurada", return_value=False):
            app.actualizar_cuadro_biblioteca()
        app.biblioteca_var.set.assert_called_once_with("")

    def test_existing_library_selection_is_preserved(self):
        app = object.__new__(library_app.App)
        app.biblioteca_var = Mock()
        selected = Path("chosen-books")
        with patch.object(library_app, "biblioteca_configurada", return_value=True), patch.object(
            library_app, "FINAL", selected,
        ):
            app.actualizar_cuadro_biblioteca()
        app.biblioteca_var.set.assert_called_once_with(str(selected))

    def test_onboarding_is_translated_in_every_supported_language(self):
        for language in TEXT.values():
            self.assertTrue(language["first_library_hint"])
            self.assertTrue(language["choose_library"])

    def test_first_use_diagnostic_refuses_to_redirect_a_running_profile(self):
        with patch.object(config_store, "app_data_dir") as profile:
            report = first_use_self_test.run_checks("0.5.3")
        profile.assert_not_called()
        self.assertFalse(report["passed"])
        self.assertIn("fresh process", report["error"])


if __name__ == "__main__":
    unittest.main()
