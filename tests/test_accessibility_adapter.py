"""Check native-property routing without pretending it proves OS-client speech."""
import tkinter as tk
import unittest
from types import SimpleNamespace

from tools.package_native_release import validate_accessibility_api_report
from ui.accessibility import expose
from ui.workspace import Workspace


class FakeWidget:
    def __init__(self, platform, supported=True):
        self.platform = platform
        self.supported = supported
        self.calls = []
        self.tk = SimpleNamespace(call=self.call)

    def _root(self):
        return self

    def __str__(self):
        return '.fixture'

    def call(self, *args):
        self.calls.append(args)
        if args[:2] == ('info', 'commands'):
            return '::tk::accessible::set_acc_role' if self.supported else ''
        if args == ('tk', 'windowingsystem'):
            return self.platform
        return ''

    def properties(self):
        return {args[0].removeprefix('::tk::accessible::set_acc_'): args[2]
                for args in self.calls if args[0].startswith('::tk::accessible::set_acc_')}


class AccessibilityAdapterTests(unittest.TestCase):
    def test_windows_and_macos_use_the_native_label_slot(self):
        for platform in ('win32', 'aqua'):
            widget = FakeWidget(platform)
            self.assertTrue(expose(widget, role='Button', name='Importar', description='Iniciar importación'))
            self.assertEqual(widget.properties()['description'], 'Importar')
            self.assertEqual(widget.properties()['help'], 'Iniciar importación')
            self.assertEqual(widget.properties()['name'], 'Importar')

    def test_atk_keeps_distinct_name_and_description(self):
        widget = FakeWidget('x11')
        expose(widget, role='Button', name='Importar', description='Iniciar importación')
        self.assertEqual(widget.properties()['name'], 'Importar')
        self.assertEqual(widget.properties()['description'], 'Iniciar importación')

    def test_macos_group_hint_identifies_the_data(self):
        widget = FakeWidget('aqua')
        expose(widget, role='Table', name='Libros', description='Seleccionar un libro')
        self.assertEqual(widget.properties()['help'], 'Libros. Seleccionar un libro')

    def test_repeated_properties_do_not_repeat_native_writes(self):
        widget = FakeWidget('win32')
        expose(widget, role='Button', name='Importar')
        count = len(widget.calls)
        expose(widget, role='Button', name='Importar')
        self.assertEqual(len(widget.calls), count)
        expose(widget, role='Button', name='Importar', state='disabled')
        self.assertEqual(widget.properties()['state'], 'disabled')

    def test_legacy_runtime_is_not_claimed_as_accessible(self):
        widget = FakeWidget('win32', supported=False)
        self.assertFalse(expose(widget, role='Button', name='Importar'))
        self.assertFalse(widget.properties())

    def test_native_error_remains_visible(self):
        widget = FakeWidget('win32')
        widget._myl_a11y_native = True
        widget._myl_a11y_errors = []
        def fail(*args):
            raise tk.TclError('Native fixture failure')
        widget.tk.call = fail
        self.assertFalse(expose(widget, role='Button', name='Importar'))
        self.assertEqual(widget._myl_a11y_errors, ['Native fixture failure'])

    def test_f6_and_shift_f6_cycle_only_visible_panes(self):
        current = [None]
        def control(visible=True):
            target = SimpleNamespace(winfo_ismapped=lambda: visible)
            target.focus_set = lambda: current.__setitem__(0, target)
            return target
        nav, center, details = control(), control(), control()
        workspace = SimpleNamespace(entity_view=control(False), tree=center, view_mode='table',
            nav_buttons={'library': nav}, detail_path_entry=details,
            root=SimpleNamespace(focus_get=lambda: current[0]))
        self.assertEqual(Workspace._cycle_pane_focus(workspace), 'break')
        self.assertIs(current[0], nav)
        Workspace._cycle_pane_focus(workspace)
        self.assertIs(current[0], center)
        Workspace._cycle_pane_focus(workspace, SimpleNamespace(state=1))
        self.assertIs(current[0], nav)
        Workspace._cycle_pane_focus(workspace, SimpleNamespace(state=1))
        self.assertIs(current[0], details)
        details.winfo_ismapped = lambda: False
        Workspace._cycle_pane_focus(workspace)
        self.assertIs(current[0], nav)

    def test_native_packaging_does_not_accept_a_boolean_only_accessibility_claim(self):
        import json
        from unittest.mock import Mock
        path = Mock()
        path.read_text.return_value = json.dumps({'passed': True, 'backend': 'tk_native', 'checks': {}})
        with self.assertRaises(ValueError):
            validate_accessibility_api_report(path)


if __name__ == '__main__':
    unittest.main()
