"""Background worker: runs git reads off the UI thread so the window never freezes.

* submit(fn, callback, key=..., low=False)
    fn runs on the worker thread; callback(result) runs on the UI thread.
    A newer job with the same key replaces an older queued one (no stale work).
    low=True jobs (prefetch) only run when no interactive job is waiting.
* LRU caches for computed diffs / commit details live here too.
"""
from __future__ import annotations

import threading
import traceback
from collections import OrderedDict

from PySide6.QtCore import QObject, Signal

from .git import LOG


class LRU:
    def __init__(self, size=300):
        self.size = size
        self._d = OrderedDict()
        self._lock = threading.Lock()

    def get(self, k, default=None):
        with self._lock:
            if k in self._d:
                self._d.move_to_end(k)
                return self._d[k]
            return default

    def __contains__(self, k):
        with self._lock:
            return k in self._d

    def put(self, k, v):
        with self._lock:
            self._d[k] = v
            self._d.move_to_end(k)
            while len(self._d) > self.size:
                self._d.popitem(last=False)

    def clear(self):
        with self._lock:
            self._d.clear()


class Worker(QObject):
    _done = Signal(object, object, object)   # callback, result, error-text

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cv = threading.Condition()
        self._high = []
        self._low = []
        self._stopped = False
        self._alive = True
        self._done.connect(self._deliver)
        self._thread = threading.Thread(target=self._run, name="gitdesk-worker", daemon=True)
        self._thread.start()

    def submit(self, fn, callback=None, key=None, low=False):
        with self._cv:
            if key is not None:
                self._high = [j for j in self._high if j[0] != key]
                self._low = [j for j in self._low if j[0] != key]
            (self._low if low else self._high).append((key, fn, callback))
            self._cv.notify()

    def pending(self):
        with self._cv:
            return len(self._high) + len(self._low)

    def _run(self):
        while True:
            with self._cv:
                while not self._stopped and not self._high and not self._low:
                    self._cv.wait()
                if self._stopped:
                    return
                key, fn, cb = (self._high or self._low).pop(0)
            try:
                res, err = fn(), None
            except Exception as e:  # report on the UI thread
                res, err = None, f"{type(e).__name__}: {e}"
                if not hasattr(e, "code"):   # GitError carries .code; others are bugs
                    err += "\n" + traceback.format_exc(limit=4)
            if self._stopped:
                return
            try:
                self._done.emit(cb, res, err)
            except RuntimeError:   # receiver already destroyed
                return

    def _deliver(self, cb, res, err):
        if not self._alive:
            return
        if err:
            from . import logger
            logger.log.warning("background task failed: " + err.strip())
            LOG.entry.emit("err", err.strip())
            return
        if cb:
            try:
                cb(res)
            except RuntimeError:
                pass          # widget closed meanwhile
            except Exception:
                from . import logger
                tb = traceback.format_exc(limit=8)
                logger.log.error("UI callback failed:\n" + tb)
                LOG.entry.emit("err", tb)

    def stop(self):
        self._alive = False
        with self._cv:
            self._stopped = True
            self._high.clear()
            self._low.clear()
            self._cv.notify_all()
