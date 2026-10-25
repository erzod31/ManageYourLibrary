"""Own-process Tk controls with a silent fake; never exercise real audio."""
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.app_speech import AppSpeech
from rounded_widgets import RoundedButton
from ui.app_speech import SpeechControls, focus_label
from ui.workspace import TEXT


class FocusLabelTests(unittest.TestCase):
    def control(self, **options):
        def option(key):
            if key not in options:
                raise tk.TclError('Unsupported fixture option')
            return options[key]
        return SimpleNamespace(cget=option, get=Mock(side_effect=AssertionError('Typed value must never be read')))

    def test_labels_and_icon_only_names_are_used_without_reading_values(self):
        widget = self.control(text='Import')
        self.assertEqual(focus_label(widget), 'Import')
        widget._myl_a11y_name = 'Search'
        self.assertEqual(focus_label(widget), 'Search')
        del widget._myl_a11y_name
        widget.accessible_name = 'Cover view'
        self.assertEqual(focus_label(widget), 'Cover view')
        widget.get.assert_not_called()

    def test_password_field_is_not_read_even_with_an_accessible_name(self):
        widget = self.control(show='*', text='Never read')
        widget._myl_a11y_name = 'Secret'
        self.assertEqual(focus_label(widget), '')
        widget.get.assert_not_called()

    def test_empty_unnamed_entry_is_silent_and_does_not_read_user_value(self):
        widget = self.control(show='')
        self.assertEqual(focus_label(widget), '')
        widget.get.assert_not_called()

    def test_all_voice_strings_are_translated(self):
        keys = {key for key in TEXT['en'] if key.startswith('speech_')}
        for language in TEXT.values():
            self.assertTrue(all(language.get(key) for key in keys))


class SpeechControlTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f'Tk display unavailable: {exc}')
        self.root.withdraw()
        self.errors = []
        self.root.report_callback_exception = lambda kind, value, _tb: self.errors.append((kind, value))
        self.voice = SimpleNamespace(speak=Mock(), stop=Mock(), close=Mock())
        self.factory = Mock(return_value=self.voice)
        self.session = AppSpeech(self.factory)
        self.workspace = SimpleNamespace(root=self.root, cards=[], labels=[],
            _button=lambda parent, text, command: RoundedButton(parent, text=text, command=command, height=38))
        self.controls = SpeechControls(self.workspace, self.root, session=self.session)
        self.controls.frame.pack(fill='x')

    def tearDown(self):
        if not hasattr(self, 'controls'):
            return
        thread = self.session._thread
        self.controls.close()
        if thread:
            thread.join(2)
            self.assertFalse(thread.is_alive())
        for identifier in self.root.tk.call('after', 'info'):
            self.root.tk.call('after', 'cancel', identifier)
        self.root.destroy()
        self.assertFalse(self.errors)

    def wait_on(self):
        with self.session._condition:
            self.assertTrue(self.session._condition.wait_for(lambda: self.session._state == 'on', timeout=2))
        self.controls._poll()

    def test_both_controls_exist_and_start_off_without_polling(self):
        self.assertEqual(self.session.state, 'off')
        self.assertEqual(self.controls.activate_button.state, 'normal')
        self.assertEqual(self.controls.deactivate_button.state, 'disabled')
        self.assertEqual(self.controls.activate_button.winfo_manager(), 'grid')
        self.assertEqual(self.controls.deactivate_button.winfo_manager(), 'grid')
        self.assertIsNone(self.controls._poll_after)
        self.assertIsNone(self.controls._focus_after)
        self.factory.assert_not_called()

    def test_only_activate_button_creates_engine_and_deactivate_closes_it(self):
        self.controls.deactivate_button.invoke()
        self.factory.assert_not_called()
        self.controls.activate_button.invoke()
        self.wait_on()
        self.factory.assert_called_once()
        self.assertEqual(self.controls.activate_button.state, 'disabled')
        self.assertEqual(self.controls.deactivate_button.state, 'normal')
        self.controls.deactivate_button.invoke()
        with self.session._condition:
            self.assertTrue(self.session._condition.wait_for(lambda: self.session._state == 'off', timeout=2))
        self.controls._poll()
        self.assertEqual(self.controls.activate_button.state, 'normal')
        self.assertEqual(self.controls.deactivate_button.state, 'disabled')
        self.voice.close.assert_called_once()
        self.voice.speak.assert_not_called()  # The withdrawn fixture has no app focus.

    def test_focus_and_selection_while_off_do_not_extract_text_or_start_engine(self):
        with patch('ui.app_speech.focus_label', side_effect=AssertionError('Off must not extract labels')):
            self.controls._focus_changed(SimpleNamespace(widget=self.root))
            self.controls._announce_focus()
            self.controls.announce_selection({'titulo': 'Synthetic book', 'autor_mostrar': 'Fixture'})
        self.factory.assert_not_called()
        self.assertIsNone(self.controls._focus_after)

    def test_leaving_app_pauses_and_drops_pending_text(self):
        self.controls.activate_button.invoke()
        self.wait_on()
        with patch.object(self.root, 'focus_displayof', return_value=None):
            self.controls._announce_focus()
        self.assertFalse(self.controls._foreground)
        self.assertEqual(self.controls.status.cget('text'), self.controls._text('paused'))
        self.assertFalse(self.session.say('Other app'))

    def test_metadata_selection_uses_only_title_and_author(self):
        self.controls.activate_button.invoke()
        self.wait_on()
        with patch.object(self.controls, '_sync_foreground'), patch.object(self.session, 'say') as say:
            self.controls.announce_selection({'titulo': 'Synthetic title', 'autor_mostrar': 'Test author',
                'ocr': 'Never read this', 'ruta': 'Never read this path', 'content': 'Never read book contents'})
        say.assert_called_once_with('Synthetic title. Test author')

    def test_close_removes_only_our_focus_bindings_and_cancels_polls(self):
        sentinel = self.root.bind_all('<FocusIn>', lambda _event: None, add='+')
        self.controls.activate_button.invoke()
        self.wait_on()
        self.assertIsNotNone(self.controls._poll_after)
        self.controls.close()
        self.assertIsNone(self.controls._poll_after)
        self.assertIsNone(self.controls._focus_after)
        self.assertIn(sentinel, self.root.bind_all('<FocusIn>'))

    def test_app_scoped_stop_shortcut_works_without_touching_an_external_reader(self):
        self.assertTrue(self.root.bind_all('<Control-Shift-Key-M>'))
        self.controls.activate_button.invoke()
        self.wait_on()
        self.assertEqual(self.controls.deactivate(SimpleNamespace(widget=self.root)), 'break')
        with self.session._condition:
            self.assertTrue(self.session._condition.wait_for(lambda: self.session._state == 'off', timeout=2))
        self.controls.close()
        self.assertFalse(self.root.bind_all('<Control-Shift-Key-M>'))

    def test_language_and_theme_updates_do_not_enable_voice(self):
        for code in TEXT:
            with patch('ui.workspace.core.IDIOMA_ACTUAL', code):
                self.controls.translate()
                self.assertEqual(self.controls.status.cget('text'), TEXT[code]['speech_off'])
                self.assertEqual(self.controls.activate_button.text, TEXT[code]['speech_activate'])
        self.assertEqual(self.session.state, 'off')
        self.factory.assert_not_called()

    def test_unavailable_platform_retains_visible_controls_without_false_success(self):
        self.session.supported = False
        self.controls._render(force=True)
        self.assertEqual(self.controls.status.cget('text'), self.controls._text('unavailable'))
        self.assertEqual(self.controls.activate_button.state, 'disabled')
        self.controls.activate_button.invoke()
        self.factory.assert_not_called()

    def test_narrow_layout_keeps_both_buttons_inside_the_bar_in_every_language(self):
        self.root.geometry('460x100')
        self.root.deiconify()
        for code in TEXT:
            with self.subTest(language=code), patch('ui.workspace.core.IDIOMA_ACTUAL', code):
                self.controls.translate()
                self.root.update()
                for button in (self.controls.activate_button, self.controls.deactivate_button):
                    self.assertTrue(button.winfo_ismapped())
                    self.assertGreaterEqual(button.winfo_x(), 0)
                    self.assertLessEqual(button.winfo_x() + button.winfo_width(), self.controls.frame.winfo_width())
        self.assertEqual(self.session.state, 'off')
        self.factory.assert_not_called()
