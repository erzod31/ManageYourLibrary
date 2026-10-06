import os
import subprocess
import threading
from contextlib import contextmanager


class OperationCancelled(RuntimeError):
    """Raised when the user requests cancellation of an active operation."""


class CancellationToken:
    """Thread-safe cooperative cancellation with external-process cleanup."""

    def __init__(self):
        self._event = threading.Event()
        self._lock = threading.RLock()
        self._processes = set()

    @property
    def cancelled(self):
        return self._event.is_set()

    def cancel(self):
        self._event.set()
        with self._lock:
            processes = list(self._processes)
        for process in processes:
            try:
                if process.poll() is None:
                    if os.name == "nt":
                        flags = subprocess.CREATE_NO_WINDOW
                        subprocess.run(
                            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                            capture_output=True, timeout=5, creationflags=flags,
                            check=False,
                        )
                    if process.poll() is None:
                        process.terminate()
            except (OSError, subprocess.SubprocessError):
                try:
                    if process.poll() is None:
                        process.kill()
                except (OSError, subprocess.SubprocessError):
                    continue

    def raise_if_cancelled(self):
        if self.cancelled:
            raise OperationCancelled("Operación cancelada por el usuario.")

    @contextmanager
    def track_process(self, process):
        with self._lock:
            self._processes.add(process)
        try:
            self.raise_if_cancelled()
            yield process
        finally:
            with self._lock:
                self._processes.discard(process)
