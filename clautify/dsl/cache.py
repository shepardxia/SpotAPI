"""Namespaced name->URI cache with fuzzy matching for the DSL layer."""

from __future__ import annotations

import collections
import difflib
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_MAX_SIZE = 5000
_SEP = "||"


class NameCache:
    """Maps (kind, lowercase_name) -> Spotify URI with fuzzy fallback.

    Optionally persists to a JSON file so cached names survive restarts.
    Uses OrderedDict for LRU eviction when max_size is exceeded.
    """

    def __init__(self, path: Optional[Path] = None, max_size: int = _MAX_SIZE):
        self._cache: collections.OrderedDict[Tuple[str, str], str] = collections.OrderedDict()
        self._reverse: Dict[str, str] = {}  # uri → name (original case)
        self._path = path
        self._max_size = max_size
        self._dirty = False
        if path:
            self._load()

    def add(self, kind: str, name: str, uri: str) -> None:
        if name and uri:
            key = (kind, name.lower().strip())
            self._cache[key] = uri
            self._cache.move_to_end(key)
            self._reverse[uri] = name
            self._dirty = True
            self._evict()

    def name_for_uri(self, uri: str) -> Optional[str]:
        """Reverse lookup: URI → original name."""
        return self._reverse.get(uri)

    def resolve(self, kind: str, name: str) -> Optional[str]:
        key = (kind, name.lower().strip())
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        # Fuzzy fallback
        candidates = [k[1] for k in self._cache if k[0] == kind]
        if not candidates:
            return None
        matches = difflib.get_close_matches(name.lower().strip(), candidates, n=1, cutoff=0.85)
        if matches:
            match_key = (kind, matches[0])
            self._cache.move_to_end(match_key)
            return self._cache[match_key]
        return None

    def add_many(self, kind: str, items: List[Tuple[str, str]]) -> None:
        """Batch add (name, uri) pairs."""
        for name, uri in items:
            self.add(kind, name, uri)

    def save(self) -> None:
        """Persist cache to disk (only if changed since last save)."""
        if not self._path or not self._dirty:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "cache": {f"{k}{_SEP}{v}": uri for (k, v), uri in self._cache.items()},
            "reverse": self._reverse,
        }
        self._path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self._dirty = False

    def _load(self) -> None:
        """Load cache from disk."""
        if not self._path or not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            for key_str, uri in raw.get("cache", {}).items():
                # Support both old NUL separator and new || separator
                if _SEP in key_str:
                    kind, name = key_str.split(_SEP, 1)
                elif "\x00" in key_str:
                    kind, name = key_str.split("\x00", 1)
                else:
                    continue
                self._cache[(kind, name)] = uri
            self._reverse = raw.get("reverse", {})
            self._evict()
        except (json.JSONDecodeError, ValueError, KeyError):
            pass  # corrupted file — start fresh

    def _evict(self) -> None:
        """Remove oldest entries if over max_size."""
        while len(self._cache) > self._max_size:
            evicted_key, evicted_uri = self._cache.popitem(last=False)
            self._reverse.pop(evicted_uri, None)
