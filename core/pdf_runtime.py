"""One process-wide lock for PDFium, including native object destruction."""
from functools import wraps
from threading import RLock

PDFIUM_LOCK = RLock()


def serialized_pdfium(function):
    @wraps(function)
    def locked(*args, **kwargs):
        with PDFIUM_LOCK:
            return function(*args, **kwargs)
    return locked
