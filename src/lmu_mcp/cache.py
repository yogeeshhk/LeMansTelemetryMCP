"""Small thread-safe LRU for derived data from one read-only recording revision."""
from collections import OrderedDict
from dataclasses import fields, is_dataclass
import sys
from threading import RLock

import numpy as np
from . import config


def _size(value, seen=None):
    """Conservative retained-size estimate for values stored by this module."""
    seen = set() if seen is None else seen
    if id(value) in seen:
        return 0
    seen.add(id(value))
    if isinstance(value, np.ndarray):
        return sys.getsizeof(value) + (value.nbytes if value.base is not None else 0)
    size = sys.getsizeof(value)
    if isinstance(value, dict):
        return size + sum(_size(k, seen) + _size(v, seen) for k, v in value.items())
    if isinstance(value, (tuple, list, set, frozenset)):
        return size + sum(_size(item, seen) for item in value)
    if is_dataclass(value) and not isinstance(value, type):
        return size + sum(_size(getattr(value, field.name), seen) for field in fields(value))
    return size


class AnalysisCache:
    def __init__(self):
        self._entries = OrderedDict()
        self._revisions = {}
        self._bytes = 0
        self._lock = RLock()

    @property
    def entry_count(self):
        with self._lock:
            return len(self._entries)

    @property
    def size_bytes(self):
        with self._lock:
            return self._bytes

    def activate(self, session_id, revision):
        with self._lock:
            if self._revisions.get(session_id) == revision:
                return
            for key in [key for key in self._entries if key[0] == session_id]:
                self._bytes -= self._entries.pop(key)[1]
            self._revisions[session_id] = revision

    def get(self, session_id, revision, kind, *parts):
        key = (session_id, revision, kind, *parts)
        with self._lock:
            if self._revisions.get(session_id) != revision or key not in self._entries:
                return None
            self._entries.move_to_end(key)
            return self._entries[key][0]

    def put(self, session_id, revision, kind, value, *parts):
        size = _size(value)
        key = (session_id, revision, kind, *parts)
        with self._lock:
            if self._revisions.get(session_id) != revision or size > config.MAX_CACHE_BYTES:
                return
            if key in self._entries:
                self._bytes -= self._entries.pop(key)[1]
            self._entries[key] = (value, size)
            self._bytes += size
            while len(self._entries) > config.MAX_CACHE_ENTRIES or self._bytes > config.MAX_CACHE_BYTES:
                self._bytes -= self._entries.popitem(last=False)[1][1]
