"""Silent lifecycle and queue tests: never instantiate SAPI or a real reader."""
import threading
import unittest
from unittest.mock import Mock

from core.app_speech import AppSpeech


class SilentVoice:
    def __init__(self):
        self.calls = []
        self.spoken = threading.Event()
        self.stopped = threading.Event()
        self.closed = threading.Event()

    def record(self, action, text=None):
        self.calls.append((action, text, threading.get_ident()))

    def speak(self, text):
        self.record('speak', text)
        self.spoken.set()

    def stop(self):
        self.record('stop')
        self.stopped.set()

    def close(self):
        self.record('close')
        self.closed.set()


class AppSpeechTests(unittest.TestCase):
    def setUp(self):
        self.sessions = []

    def tearDown(self):
        for session in self.sessions:
            thread = session._thread
            session.close()
            if thread is not None:
                thread.join(2)
                self.assertFalse(thread.is_alive(), 'Silent worker did not terminate')

    def session(self, factory=None, **kwargs):
        voice = SilentVoice()
        session = AppSpeech(factory or (lambda: voice), **kwargs)
        self.sessions.append(session)
        return session, voice

    def state(self, session, expected):
        with session._condition:
            self.assertTrue(session._condition.wait_for(lambda: session._state == expected, timeout=2),
                            f'Expected {expected}, got {session._state}')

    def test_default_is_off_without_engine_worker_or_retained_text(self):
        factory = Mock()
        session, _ = self.session(factory)
        session.set_foreground(True)
        self.assertEqual(session.state, 'off')
        self.assertFalse(session.active)
        self.assertIsNone(session._thread)
        self.assertFalse(session.say('Private fixture'))
        self.assertIsNone(session._pending)
        factory.assert_not_called()

    def test_unsupported_platform_cannot_start(self):
        factory = Mock()
        session, _ = self.session(factory, supported=False)
        self.assertFalse(session.activate())
        factory.assert_not_called()

    def test_explicit_activation_is_required_and_uses_owned_worker(self):
        session, voice = self.session()
        session.set_foreground(True)
        self.assertTrue(session.activate())
        self.state(session, 'on')
        self.assertTrue(session.say('Library'))
        self.assertTrue(voice.spoken.wait(2))
        session.deactivate()
        self.state(session, 'off')
        self.assertEqual([(a, t) for a, t, _ in voice.calls], [('speak', 'Library'), ('close', None)])
        self.assertEqual(len({tid for _, _, tid in voice.calls}), 1)
        self.assertNotEqual(voice.calls[0][2], threading.get_ident())

    def test_foreground_is_required(self):
        session, voice = self.session()
        session.activate()
        self.state(session, 'on')
        self.assertFalse(session.say('Should not be read'))
        session.deactivate()
        self.state(session, 'off')
        self.assertFalse(voice.spoken.is_set())

    def delayed(self):
        ready, release = threading.Event(), threading.Event()
        voice = SilentVoice()
        def factory():
            ready.set()
            if not release.wait(2):
                raise TimeoutError('Fixture gate')
            return voice
        session, _ = self.session(factory)
        session.set_foreground(True)
        session.activate()
        self.assertTrue(ready.wait(2))
        self.addCleanup(release.set)
        return session, voice, release

    def test_deactivate_during_initialization_cannot_utter_queued_text(self):
        session, voice, release = self.delayed()
        session.say('Queued before cancellation')
        session.deactivate()
        self.assertEqual(session.state, 'stopping')
        self.assertFalse(session.say('Queued after cancellation'))
        self.assertFalse(session.activate())
        release.set()
        self.state(session, 'off')
        self.assertFalse(voice.spoken.is_set())
        self.assertTrue(voice.closed.is_set())

    def test_only_latest_pending_announcement_survives(self):
        session, voice, release = self.delayed()
        for index in range(100):
            self.assertTrue(session.say(f'Control {index}'))
        release.set()
        self.assertTrue(voice.spoken.wait(2))
        session.deactivate()
        self.state(session, 'off')
        self.assertEqual([text for action, text, _ in voice.calls if action == 'speak'], ['Control 99'])

    def test_focus_loss_drops_queued_text_and_purges_owned_voice(self):
        session, voice, release = self.delayed()
        session.say('Stale focus')
        session.set_foreground(False)
        release.set()
        self.assertTrue(voice.stopped.wait(2))
        self.assertFalse(voice.spoken.is_set())
        self.assertFalse(session.say('Another app'))
        session.set_foreground(True)
        self.assertTrue(session.say('Fresh focus'))
        self.assertTrue(voice.spoken.wait(2))

    def test_no_duplicate_worker_or_automatic_reactivation(self):
        factory = Mock(return_value=SilentVoice())
        session, _ = self.session(factory)
        session.activate()
        self.state(session, 'on')
        self.assertFalse(session.activate())
        factory.assert_called_once()
        session.deactivate()
        self.state(session, 'off')
        session.set_foreground(True)
        self.assertFalse(session.say('Still off'))
        factory.assert_called_once()
        self.assertTrue(session.activate())
        self.state(session, 'on')
        self.assertEqual(factory.call_count, 2)

    def test_new_session_is_off_after_previous_was_enabled(self):
        session, _ = self.session()
        session.activate()
        self.state(session, 'on')
        other, _ = self.session()
        self.assertEqual(other.state, 'off')
        self.assertIsNone(other._thread)

    def test_engine_failure_is_visible_not_retried_automatically(self):
        factory = Mock(side_effect=OSError('Synthetic voice unavailable'))
        session, _ = self.session(factory)
        session.activate()
        self.state(session, 'error')
        self.assertFalse(session.active)
        self.assertIsNone(session._pending)
        factory.assert_called_once()

    def test_speech_error_closes_owned_engine(self):
        voice = SilentVoice()
        voice.speak = Mock(side_effect=OSError('Synthetic speech error'))
        session, _ = self.session(lambda: voice)
        session.set_foreground(True)
        session.activate()
        self.state(session, 'on')
        session.say('Synthetic label')
        self.state(session, 'error')
        self.assertTrue(voice.closed.is_set())

    def test_text_is_plain_short_normalized_and_not_retained_on_close(self):
        session, voice, release = self.delayed()
        session.say('\x00  Library\n\t' + 'x' * 600)
        release.set()
        self.assertTrue(voice.spoken.wait(2))
        text = voice.calls[0][1]
        self.assertEqual(len(text), 400)
        self.assertTrue(text.startswith('Library x'))
        self.assertNotIn('\x00', text)
        session.close()
        self.state(session, 'closed')
        self.assertIsNone(session._pending)
        self.assertFalse(session.activate())

    def test_close_is_idempotent_and_never_starts_a_backend(self):
        factory = Mock()
        session, _ = self.session(factory)
        session.close()
        session.close()
        self.assertEqual(session.state, 'closed')
        self.assertFalse(session.activate())
        factory.assert_not_called()
