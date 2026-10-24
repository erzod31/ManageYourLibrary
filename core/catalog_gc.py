"""Keep a large, long-lived catalog out of repeated cyclic-GC scans.

Reference counting still releases replaced rows immediately; cyclic GC stays
enabled for new objects. Ownership is explicit and released on UI shutdown.
"""
import gc


class CatalogGcGuard:
    _active = False

    def __init__(self, count, threshold=10_000):
        self.owned = False
        if count >= threshold and gc.isenabled() and not type(self)._active:
            # Pay the full scan once during initialization, not on mouse events.
            # The standalone app owns this interpreter. CPython's startup may
            # already have a small permanent generation; that is not a second
            # app lease. All generations are returned to ordinary GC on close.
            gc.collect()
            gc.freeze()
            self.owned = True
            type(self)._active = True

    def include_new_snapshot(self):
        if self.owned:
            gc.collect(0)
            gc.freeze()

    def close(self):
        if self.owned:
            gc.unfreeze()
            self.owned = False
            type(self)._active = False
