"""Stable file identities used by duplicate and transaction safeguards."""

from __future__ import annotations

import hashlib
from pathlib import Path


class FileChangedDuringReadError(OSError):
    """Raised when a file identity changes while its digest is being read."""


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    """Return the complete SHA-256 digest of a live file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(block_size):
            digest.update(chunk)
    return digest.hexdigest()


def partial_file_signature(path: Path, block_size: int = 256 * 1024) -> str:
    """Return a bounded signature based on size plus the first and last blocks."""
    path = Path(path)
    stat = path.stat()
    digest = hashlib.sha256()
    digest.update(str(stat.st_size).encode("ascii", errors="ignore"))
    with path.open("rb") as stream:
        digest.update(stream.read(block_size))
        if stat.st_size > block_size:
            stream.seek(max(0, stat.st_size - block_size))
            digest.update(stream.read(block_size))
    return digest.hexdigest()


def _live_signature(path: Path) -> tuple[int, int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def validated_sha256_file(path: Path, block_size: int = 1024 * 1024) -> tuple[int, str]:
    """Return size and digest only when the live file stayed unchanged."""
    path = Path(path)
    before = _live_signature(path)
    digest = sha256_file(path, block_size=block_size)
    after = _live_signature(path)
    if before != after:
        raise FileChangedDuringReadError(f"File changed while hashing: {path}")
    return before[0], digest


def live_files_identical(first: Path, second: Path) -> bool:
    """Compare current contents and reject a result if either file changed mid-read."""
    try:
        first = Path(first)
        second = Path(second)
        if not first.is_file() or not second.is_file():
            return False

        if _live_signature(first)[0] != _live_signature(second)[0]:
            return False
        first_size, first_hash = validated_sha256_file(first)
        second_size, second_hash = validated_sha256_file(second)
        if first_size != second_size:
            return False
        return first_hash == second_hash
    except OSError:
        return False
