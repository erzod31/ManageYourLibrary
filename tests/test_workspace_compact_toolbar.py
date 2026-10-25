"""Responsive layout routing without OS input or a personal catalog."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from ui.workspace import Workspace, _text


class LayoutWidget:
    def __init__(self, width):
        self.width = width
        self.pack = Mock()
        self.pack_forget = Mock()
        self.grid = Mock()

    def winfo_reqwidth(self):
        return self.width

    def winfo_width(self):
        return self.width


class CompactToolbarTests(unittest.TestCase):
    def workspace(self, width):
        target = object.__new__(Workspace)
        target._toolbar_after = None
        target._toolbar_compact = None
        target.filter_bar = LayoutWidget(width)
        target.filter_buttons = {key: LayoutWidget(60) for key in ('all', 'EPUB', 'PDF', 'other')}
        target.format_combo = LayoutWidget(110)
        target.sort_group = LayoutWidget(180)
        target.action_group = LayoutWidget(320)
        return target

    def test_narrow_view_uses_combobox_and_second_action_row(self):
        target = self.workspace(472)
        target._fit_library_toolbar()
        self.assertTrue(target._toolbar_compact)
        target.format_combo.pack.assert_called_once()
        self.assertTrue(all(widget.pack_forget.called for widget in target.filter_buttons.values()))
        self.assertEqual(target.action_group.grid.call_args.kwargs['row'], 1)

    def test_wide_view_preserves_format_buttons_and_one_row(self):
        target = self.workspace(1100)
        target._fit_library_toolbar()
        self.assertFalse(target._toolbar_compact)
        self.assertTrue(all(widget.pack.called for widget in target.filter_buttons.values()))
        self.assertEqual(target.action_group.grid.call_args.kwargs['row'], 0)

    def test_resize_coalesces_and_same_band_does_not_repack(self):
        target = self.workspace(472)
        target.root = SimpleNamespace(after_idle=Mock(return_value='scheduled'))
        target._schedule_toolbar_fit()
        target._schedule_toolbar_fit()
        target.root.after_idle.assert_called_once()
        target._fit_library_toolbar()
        count = target.action_group.grid.call_count
        target._fit_library_toolbar()
        self.assertEqual(target.action_group.grid.call_count, count)
        target.filter_bar.width = 1100
        target._fit_library_toolbar()
        self.assertFalse(target._toolbar_compact)

    def test_combo_maps_localized_all_other_and_exact_formats(self):
        target = self.workspace(472)
        target.set_format_filter = Mock()
        for label, expected in ((_text('all_formats'), 'all'), (_text('other_formats'), 'other'), ('EPUB', 'EPUB'), ('DJVU', 'DJVU')):
            target.format_var = SimpleNamespace(get=lambda label=label: label)
            target._on_format_combo_selected()
            target.set_format_filter.assert_called_with(expected)

    def test_status_strip_reserves_cancel_space_and_coalesces_width_band(self):
        target = object.__new__(Workspace)
        target._status_strip_compact = None
        target.app = SimpleNamespace(barra_progreso=Mock(), label_estado_titulo=Mock())
        target._fit_activity_strip(SimpleNamespace(width=472))
        target.app.barra_progreso.configure.assert_called_once_with(length=100)
        target.app.label_estado_titulo.grid_remove.assert_called_once()
        target._fit_activity_strip(SimpleNamespace(width=480))
        target.app.barra_progreso.configure.assert_called_once()
        target._fit_activity_strip(SimpleNamespace(width=900))
        target.app.barra_progreso.configure.assert_called_with(length=180)
        target.app.label_estado_titulo.grid.assert_called_once()
