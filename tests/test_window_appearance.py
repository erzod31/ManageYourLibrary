"""Check per-window Windows decorations using doubles, never OS preferences."""
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from library_app import App


class AppearanceWindow:
    def __init__(self, *, platform='win32', mapped=True, popup=False, exists=True, supported=True):
        self.tk = SimpleNamespace(call=lambda *_args: platform)
        self.mapped = mapped
        self.popup = popup
        self.exists = exists
        self.supported = supported
        self.children = []
        self.attributes = []
        self.pending = []

    def winfo_exists(self):
        return self.exists

    def winfo_ismapped(self):
        return self.mapped

    def overrideredirect(self):
        return self.popup

    def winfo_children(self):
        return self.children

    def wm_attributes(self, *args):
        if not self.supported:
            raise tk.TclError('bad attribute "-appearance"')
        self.attributes.append(args)

    def after_idle(self, callback):
        self.pending.append(callback)


class WindowAppearanceTests(unittest.TestCase):
    def app(self, theme='contrast', window=None):
        app = object.__new__(App)
        app.root = AppearanceWindow() if window is None else window
        app.theme_preference = theme
        app.modo_oscuro = theme in {'dark', 'contrast'}
        return app

    def test_contrast_and_dark_use_dark_decorations(self):
        for theme in ('contrast', 'dark'):
            app = self.app(theme)
            app._sync_window_appearance()
            self.assertEqual(app.root.attributes, [('-appearance', 'dark')])

    def test_light_and_system_modes_are_explicit(self):
        for theme, expected in (('light', 'light'), ('system', 'auto')):
            app = self.app(theme)
            app._sync_window_appearance()
            self.assertEqual(app.root.attributes, [('-appearance', expected)])

    def test_other_platforms_are_not_changed(self):
        for platform in ('aqua', 'x11'):
            app = self.app(window=AppearanceWindow(platform=platform))
            app._sync_window_appearance()
            self.assertEqual(app.root.attributes, [])

    def test_legacy_tk_fails_without_interrupting_theme(self):
        app = self.app(window=AppearanceWindow(supported=False))
        app._sync_window_appearance()
        self.assertEqual(app.root.attributes, [])

    def test_unmapped_or_destroyed_windows_are_not_touched(self):
        for options in ({'mapped': False}, {'exists': False}):
            app = self.app(window=AppearanceWindow(**options))
            app._sync_window_appearance()
            self.assertEqual(app.root.attributes, [])

    def test_editor_and_nested_dialogs_receive_same_appearance(self):
        app = self.app()
        editor, nested = AppearanceWindow(), AppearanceWindow()
        app.root.children = [editor]
        editor.children = [nested]
        with patch('library_app.tk.Toplevel', AppearanceWindow):
            app._sync_window_appearance()
        self.assertEqual(editor.attributes, [('-appearance', 'dark')])
        self.assertEqual(nested.attributes, [('-appearance', 'dark')])

    def test_borderless_popup_is_not_given_titlebar_attributes(self):
        app = self.app(window=AppearanceWindow(popup=True))
        app._sync_window_appearance()
        self.assertEqual(app.root.attributes, [])

    def test_map_waits_for_native_wrapper_before_applying(self):
        app = self.app()
        editor = AppearanceWindow()
        with patch('library_app.tk.Toplevel', AppearanceWindow):
            app._sync_mapped_window_appearance(SimpleNamespace(widget=editor))
        self.assertEqual(editor.attributes, [])
        self.assertEqual(len(editor.pending), 1)
        editor.pending[0]()
        self.assertEqual(editor.attributes, [('-appearance', 'dark')])


if __name__ == '__main__':
    unittest.main()
