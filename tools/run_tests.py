"""Run the complete test suite in a disposable profile, even for legacy tests."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    from core import config_store
    with tempfile.TemporaryDirectory(prefix="myl_tests_") as directory:
        profile = Path(directory) / "profile"
        with patch.object(config_store, 'app_data_dir', return_value=profile), patch.dict(
                os.environ, {'APPDATA': directory, 'LOCALAPPDATA': directory,
                             'XDG_DATA_HOME': directory, 'PYTHONDONTWRITEBYTECODE': '1',
                             'MANAGE_YOUR_LIBRARY_PROFILE': str(profile)}):
            # Tests must never block unattended CI on a modal error dialog.
            with patch('tkinter.messagebox.showerror', side_effect=AssertionError('Unexpected GUI error dialog')):
                suite = unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parents[1] / 'tests'))
                result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
