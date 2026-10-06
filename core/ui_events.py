"""Thread-safe handoff of callbacks to the Tk main thread."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from queue import Empty, Queue
from typing import Any, NamedTuple


class _QueuedCall(NamedTuple):
    callback: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


class UiEventQueue:
    """Collect worker callbacks and execute them only from the owner thread."""

    def __init__(self, main_thread_id: int | None = None) -> None:
        self._events: Queue[_QueuedCall] = Queue()
        self._main_thread_id = main_thread_id or threading.get_ident()

    def post(self, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        self._events.put(_QueuedCall(callback, args, kwargs))

    def drain(self, limit: int = 100, *, time_budget_ms: float | None = None) -> int:
        if threading.get_ident() != self._main_thread_id:
            raise RuntimeError("UI events must be drained from the main thread")

        processed = 0
        deadline = None if time_budget_ms is None else time.perf_counter() + max(0, time_budget_ms) / 1000
        while processed < limit:
            if processed and deadline is not None and time.perf_counter() >= deadline:
                break
            try:
                event = self._events.get_nowait()
            except Empty:
                break
            event.callback(*event.args, **event.kwargs)
            processed += 1
        return processed

    def empty(self) -> bool:
        return self._events.empty()
