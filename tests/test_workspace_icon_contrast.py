"""Check icon foreground selection without raster generation or a GUI."""
import unittest
from types import SimpleNamespace

from ui.workspace import Workspace


class IconButton:
    def __init__(self):
        self.options = {}

    def configure(self, **options):
        self.options.update(options)


class WorkspaceIconContrastTests(unittest.TestCase):
    def workspace(self, colors, view='covers'):
        workspace = object.__new__(Workspace)
        workspace.app = SimpleNamespace(tema_actual=colors, modo_oscuro=True, btn_tema=IconButton())
        workspace.cover_button = IconButton()
        workspace.table_button = IconButton()
        workspace.view_mode = view
        workspace._icon_photo = lambda name, color, size=24: (name, color, size)
        return workspace

    def test_selected_view_icon_matches_primary_foreground_in_all_palettes(self):
        for name, text, primary_text, primary_bg in (
                ('light', '#2d2a27', '#ffffff', '#a9573e'),
                ('dark', '#f4eee7', '#1d1612', '#c9785b'),
                ('contrast', '#ffffff', '#000000', '#ffff00')):
            with self.subTest(palette=name):
                workspace = self.workspace({'text': text, 'primary_text': primary_text, 'primary_bg': primary_bg})
                workspace._update_view_state()
                self.assertEqual(workspace.cover_button.options['image'], ('grid', primary_text, 24))
                self.assertEqual(workspace.cover_button.options['fg'], primary_text)
                self.assertEqual(workspace.cover_button.options['bg'], primary_bg)
                self.assertEqual(workspace.table_button.options['image'], ('list', text, 24))

    def test_switching_view_recolors_both_icons_without_changing_theme(self):
        workspace = self.workspace({'text': '#ffffff', 'primary_text': '#000000', 'primary_bg': '#ffff00'})
        workspace._update_view_state()
        workspace.view_mode = 'table'
        workspace._update_view_state()
        self.assertEqual(workspace.cover_button.options['image'], ('grid', '#ffffff', 24))
        self.assertEqual(workspace.table_button.options['image'], ('list', '#000000', 24))

    def test_primary_open_icon_uses_black_in_high_contrast(self):
        colors = {'text': '#ffffff', 'primary_text': '#000000', 'accent': '#00ffff'}
        workspace = self.workspace(colors)
        primary = IconButton()
        secondary = IconButton()
        workspace.brand_icon_label = IconButton()
        workspace._icon_bindings = [(primary, 'open', 'primary', 24), (secondary, 'edit', 'secondary', 24)]
        workspace._refresh_bound_icons(colors)
        self.assertEqual(primary.options['image'], ('open', '#000000', 24))
        self.assertEqual(secondary.options['image'], ('edit', '#ffffff', 24))


if __name__ == '__main__':
    unittest.main()
