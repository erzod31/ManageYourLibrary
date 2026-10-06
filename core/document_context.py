import threading
from dataclasses import dataclass, field
from pathlib import Path

from .file_transactions import calcular_sha256_archivo


@dataclass
class DocumentContext:
    """Memoized, provenance-aware view of one immutable file snapshot."""

    path: Path
    _size: int = field(init=False)
    _mtime_ns: int = field(init=False)
    _sha256: str | None = field(default=None, init=False)
    _values: dict = field(default_factory=dict, init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    def __post_init__(self):
        self.path = Path(self.path)
        stat = self.path.stat()
        self._size = stat.st_size
        self._mtime_ns = stat.st_mtime_ns

    @property
    def size(self):
        return self._size

    @property
    def mtime_ns(self):
        return self._mtime_ns

    @property
    def sha256(self):
        with self._lock:
            self.assert_unchanged()
            if self._sha256 is None:
                self._sha256 = calcular_sha256_archivo(self.path)
            return self._sha256

    def assert_unchanged(self):
        stat = self.path.stat()
        if stat.st_size != self._size or stat.st_mtime_ns != self._mtime_ns:
            raise RuntimeError(f"El documento cambió durante el análisis: {self.path}")

    def memoize(self, key, factory):
        with self._lock:
            self.assert_unchanged()
            if key not in self._values:
                self._values[key] = factory()
            return self._values[key]

    def signature(self):
        return {"size": self.size, "mtime_ns": self.mtime_ns, "sha256": self.sha256}
