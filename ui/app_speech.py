"""Visible, explicit controls for this app's optional local UI voice.

This supplements, and never switches off, passive platform accessibility.
Tests inject a silent backend; they must not click Activate with a real voice.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

from core.app_speech import AppSpeech
from ui.accessibility import name_control


def focus_label(widget):
    """Read a control label, never typed values, passwords, logs or book text."""
    def option(key):
        try:
            return widget.cget(key)
        except (AttributeError, tk.TclError):
            return ''
    if option('show'):
        return ''
    return (getattr(widget, '_myl_a11y_name', '')
            or getattr(widget, 'accessible_name', '') or str(option('text') or ''))


class SpeechControls:
    def __init__(self, workspace, parent, *, session=None):
        self.workspace = workspace
        self.root = workspace.root
        self.session = session if session is not None else AppSpeech()
        self._poll_after = None
        self._focus_after = None
        self._closed = False
        self._foreground = False
        self._last_render = None
        self.frame = tk.Frame(parent, height=50, bd=1, highlightthickness=1)
        self.frame.pack_propagate(False)
        self.frame.grid_propagate(False)
        self.frame.columnconfigure(0, weight=1)
        self.status = tk.Label(self.frame, anchor='w', font=('Segoe UI', 9), bd=0, wraplength=190)
        self.status.grid(row=0, column=0, sticky='w', padx=(12, 6), pady=6)
        self.activate_button = workspace._button(self.frame, '', self.activate)
        self.activate_button.grid(row=0, column=1, padx=(0, 6), pady=5)
        self.deactivate_button = workspace._button(self.frame, '', self.deactivate)
        self.deactivate_button.grid(row=0, column=2, padx=(0, 8), pady=5)
        workspace.cards.append(self.frame)
        workspace.labels.append(self.status)
        self._bindings = []
        for sequence, callback in (('<FocusIn>', self._focus_changed), ('<FocusOut>', self._focus_changed),
                                   ('<Control-Shift-Key-M>', self.deactivate)):
            binding = self.root.bind_all(sequence, callback, add='+')
            self._bindings.append((sequence, binding))
        self.frame.bind('<Configure>', self._resize, add='+')
        self.translate()

    def _text(self, key):
        # Import only at use time to avoid a workspace/control import cycle.
        from ui.workspace import _text
        return _text('speech_' + key)

    def translate(self):
        for button, key in ((self.activate_button, 'activate'), (self.deactivate_button, 'deactivate')):
            text = self._text(key)
            font = tkfont.Font(root=self.root, font=button.font)
            button.configure(text=text, accessible_name=text + ': ' + self._text('title'),
                             width=max(82, font.measure(text) + 30), height=max(36, font.metrics('linespace') + 14))
        self._render(force=True)
        self._resize()

    def _resize(self, event=None):
        width = event.width if event is not None else self.frame.winfo_width()
        if width <= 1:
            return
        available = width - self.activate_button.winfo_reqwidth() - self.deactivate_button.winfo_reqwidth() - 36
        status_font = tkfont.Font(root=self.root, font=self.status.cget('font'))
        stacked = available < min(190, status_font.measure(self.status.cget('text')) + 4)
        wrap = max(60, width - 24 if stacked else available)
        signature = (stacked, wrap, self.status.cget('text'))
        if getattr(self, '_layout_signature', None) == signature:
            return
        self._layout_signature = signature
        self.status.grid_configure(row=0, column=0, columnspan=3 if stacked else 1, sticky='ew')
        self.activate_button.grid_configure(row=1 if stacked else 0)
        self.deactivate_button.grid_configure(row=1 if stacked else 0)
        self.status.configure(wraplength=wrap)
        label_height = self.status.winfo_reqheight() + 12
        buttons_height = max(self.activate_button.winfo_reqheight(), self.deactivate_button.winfo_reqheight()) + 10
        self.frame.configure(height=max(50, (label_height + buttons_height if stacked
                                            else max(label_height, buttons_height)) + 4))

    def _render(self, *, force=False):
        state = self.session.state
        display = 'unavailable' if not self.session.supported else 'paused' if state == 'on' and not self._foreground else state
        if not force and display == self._last_render:
            return
        self._last_render = display
        self.status.configure(text=self._text(display if display != 'closed' else 'off'))
        name_control(self.status, self.status.cget('text'), self._text('help'))
        self.activate_button.configure(state='normal' if self.session.supported and state in {'off', 'error'} else 'disabled')
        self.deactivate_button.configure(state='normal' if state in {'starting', 'on'} else 'disabled')
        self._resize()

    def _sync_foreground(self):
        try:
            self._foreground = self.root.focus_displayof() is not None
        except (KeyError, tk.TclError):
            self._foreground = False
        self.session.set_foreground(self._foreground)

    def activate(self):
        if self._closed:
            return
        self._sync_foreground()
        if self.session.activate():
            self.session.say(self._text('on'))
            self._poll()

    def deactivate(self, _event=None):
        if self._closed:
            return 'break'
        self.session.deactivate()
        self._cancel('_focus_after')
        self._poll()
        return 'break'

    def _poll(self):
        self._cancel('_poll_after')
        if self._closed:
            return
        self._render()
        if self.session.state in {'starting', 'on', 'stopping'}:
            self._poll_after = self.root.after(100, self._poll)

    def _focus_changed(self, _event):
        if self._closed or not self.session.active:
            return  # Off means no extraction, engine, polling or queued text.
        self._cancel('_focus_after')
        self._focus_after = self.root.after_idle(self._announce_focus)

    def _announce_focus(self):
        self._focus_after = None
        if self._closed or not self.session.active:
            return
        self._sync_foreground()
        self._render()
        if self._foreground:
            try:
                widget = self.root.focus_get()
                if isinstance(widget, tk.Misc):
                    self.session.say(focus_label(widget))
            except (KeyError, tk.TclError):
                pass

    def announce_selection(self, item):
        if not self.session.active or not item:
            return
        self._sync_foreground()
        self.session.say('. '.join(str(item.get(key) or '') for key in ('titulo', 'autor_mostrar')))

    def _cancel(self, attribute):
        pending = getattr(self, attribute)
        if pending is not None:
            try:
                self.root.after_cancel(pending)
            except tk.TclError:
                pass
            setattr(self, attribute, None)

    def close(self):
        self._closed = True
        self._cancel('_poll_after')
        self._cancel('_focus_after')
        self.session.close()
        # Remove only our callback scripts, not other all-tag focus bindings.
        for sequence, binding in self._bindings:
            if binding:
                self.root._unbind(('bind', 'all', sequence), binding)
        self._bindings.clear()
