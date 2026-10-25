"""Opt-in, session-only speech. Never starts or controls an external reader.

No backend, COM object, or worker exists before the user's explicit activation.
Only the newest short UI announcement is retained; no book text is collected.
"""
from __future__ import annotations

import sys
import threading


def _windows_backend():
    from core.sapi_speech import WindowsVoice
    return WindowsVoice()


class AppSpeech:
    def __init__(self, backend_factory=None, *, supported=None):
        self.supported = (sys.platform == 'win32' if supported is None else supported)
        if backend_factory is not None and supported is None:
            self.supported = True
        self._factory = backend_factory or _windows_backend
        self._condition = threading.Condition()
        self._state = 'off'
        self._thread = None
        self._closed = False
        self._stop = False
        self._foreground = False
        self._purge = False
        self._pending = None

    @property
    def state(self):
        with self._condition:
            return self._state

    @property
    def active(self):
        return self.state in {'starting', 'on'}

    def activate(self):
        """The UI calls this only from its explicit Activate button."""
        with self._condition:
            if not self.supported or self._closed or self._thread is not None:
                return False
            self._stop = False
            self._pending = None
            self._purge = False
            self._state = 'starting'
            self._thread = threading.Thread(target=self._run, name='app-local-voice', daemon=True)
            try:
                self._thread.start()
            except RuntimeError:
                self._thread = None
                self._state = 'error'
                return False
            return True

    def deactivate(self):
        """Discard pending speech immediately; purge the owned engine off-Tk."""
        with self._condition:
            self._pending = None
            self._stop = True
            self._state = 'stopping' if self._thread is not None else ('closed' if self._closed else 'off')
            self._condition.notify_all()

    def set_foreground(self, active):
        with self._condition:
            self._foreground = bool(active)
            if not active:
                self._pending = None
                self._purge = True
                self._condition.notify_all()

    def say(self, text):
        with self._condition:
            if self._state not in {'starting', 'on'} or self._stop or not self._foreground:
                return False
            # Plain, bounded UI text only. Never treat text as a file or XML.
            text = ' '.join(str(text).replace('\x00', '').split())[:400]
            if not text:
                return False
            self._pending = text
            self._condition.notify_all()
            return True

    def close(self):
        with self._condition:
            self._closed = True
            self.deactivate()

    def _run(self):
        backend = None
        failed = False
        try:
            backend = self._factory()
            with self._condition:
                if not self._stop:
                    self._state = 'on'
                self._condition.notify_all()
            while True:
                with self._condition:
                    self._condition.wait_for(lambda: self._stop or self._purge or self._pending is not None)
                    if self._stop:
                        break
                    purge = self._purge
                    self._purge = False
                    text = None
                    if not purge:
                        text = self._pending if self._foreground else None
                        self._pending = None
                if purge:
                    backend.stop()
                elif text:
                    # Check again after leaving the queue lock. Backend calls
                    # are asynchronous and never hold a lock needed by Tk.
                    with self._condition:
                        allowed = not self._stop and self._foreground
                    if allowed:
                        backend.speak(text)
        except Exception:
            failed = True  # Do not retain/log UI text or native exception paths.
        finally:
            if backend is not None:
                try:
                    backend.close()
                except Exception:
                    failed = True
            with self._condition:
                self._pending = None
                self._thread = None
                self._state = 'closed' if self._closed else 'error' if failed and not self._stop else 'off'
                self._condition.notify_all()
