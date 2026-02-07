"""Spotify DSL parser — Lark grammar + transformer → command dict."""

from pathlib import Path
from typing import Any, Dict

from lark import Lark, Token, Transformer

_GRAMMAR = (Path(__file__).parent / "grammar.lark").read_text()

_parser = Lark(_GRAMMAR, parser="earley", ambiguity="resolve")


class SpotifyTransformer(Transformer):
    """Transforms a Lark parse tree into a flat command dict."""

    def _cmd(self, action: str, **kwargs: Any) -> Dict[str, Any]:
        return {"action": action, **{k: v for k, v in kwargs.items() if v is not None}}

    def _query(self, query: str, **kwargs: Any) -> Dict[str, Any]:
        return {"query": query, **{k: v for k, v in kwargs.items() if v is not None}}

    # --- terminals ---

    def URI(self, t: Token) -> str:
        return str(t)

    def ESCAPED_STRING(self, t: Token) -> str:
        return str(t)[1:-1]

    def NUMBER(self, t: Token) -> float:
        return float(t)

    def SIGNED_NUMBER(self, t: Token) -> int:
        return int(t)

    def VOL_DELTA(self, t: Token) -> int:
        return int(t)

    def MODE(self, t: Token) -> str:
        return str(t).lower()

    def TYPE_KW(self, t: Token) -> str:
        return str(t).lower()

    def type(self, items: list) -> str:
        return items[0]

    # --- actions ---

    def play(self, items):
        target = items[0]
        context = items[1] if len(items) > 1 else None
        return self._cmd("play", target=target, context=context)

    def pause(self, items):
        return self._cmd("pause")

    def resume(self, items):
        return self._cmd("resume")

    def skip(self, items):
        return self._cmd("skip", n=items[0] if items else 1)

    def seek(self, items):
        return self._cmd("seek", position_ms=items[0])

    def queue(self, items):
        return self._cmd("queue", target=items[0])

    def like(self, items):
        return self._cmd("like", target=items[0])

    def unlike(self, items):
        return self._cmd("unlike", target=items[0])

    def follow(self, items):
        return self._cmd("follow", target=items[0])

    def unfollow(self, items):
        return self._cmd("unfollow", target=items[0])

    def save(self, items):
        return self._cmd("save", target=items[0])

    def unsave(self, items):
        return self._cmd("unsave", target=items[0])

    def playlist_add(self, items):
        return self._cmd("playlist_add", track=items[0], playlist=items[1])

    def playlist_remove(self, items):
        return self._cmd("playlist_remove", track=items[0], playlist=items[1])

    def playlist_create(self, items):
        return self._cmd("playlist_create", name=items[0])

    def playlist_delete(self, items):
        return self._cmd("playlist_delete", target=items[0])

    # --- queries ---

    def search(self, items):
        return self._query("search", term=items[0], type=items[1] if len(items) > 1 else None)

    def now_playing(self, items):
        return self._query("now_playing")

    def get_queue(self, items):
        return self._query("get_queue")

    def get_devices(self, items):
        return self._query("get_devices")

    def library(self, items):
        return self._query("library", type=items[0] if items else None)

    def info(self, items):
        return self._query("info", target=items[0])

    def history(self, items):
        return self._query("history")

    def recommend(self, items):
        if len(items) == 2:
            return self._query("recommend", n=int(items[0]), target=items[1])
        return self._query("recommend", target=items[0])

    # --- modifiers (all return (key, value) tuples) ---

    def volume(self, items):
        return ("volume", items[0])

    def volume_rel(self, items):
        return ("volume_rel", items[0])

    def mode(self, items):
        return ("mode", items[0])

    def device(self, items):
        return ("device", items[0])

    def limit(self, items):
        return ("limit", int(items[0]))

    def offset(self, items):
        return ("offset", int(items[0]))

    # --- root ---

    def start(self, items):
        if isinstance(items[0], dict):
            result = items[0]
            modifiers = items[1:]
        else:
            result = {"action": "set"}
            modifiers = items

        for key, val in modifiers:
            result[key] = val

        return result


def parse(command: str) -> Dict[str, Any]:
    """Parse a DSL command string into a command dict."""
    tree = _parser.parse(command)
    return SpotifyTransformer().transform(tree)
