"""Spotify DSL — session-based command interface.

Usage:
    from clautify.dsl import SpotifySession

    # One-time setup — paste sp_dc from browser dev tools:
    SpotifySession.setup("AQBF7J2...")

    # Every subsequent use — auto-loads from ~/.config/clautify/session.json:
    session = SpotifySession.from_config()

    result = session.run('play "Bohemian Rhapsody" volume 70 mode shuffle')
    result = session.run('search "jazz" artists limit 5')
    result = session.run('add spotify:track:abc to "Road Trip"')

    session.close()
"""

import json
from pathlib import Path
from typing import Any, Dict, Union

from lark.exceptions import UnexpectedInput

from clautify.dsl.executor import DSLError, SpotifyExecutor
from clautify.dsl.parser import parse
from clautify.login import Login
from clautify.types import Config
from clautify.utils.logger import NoopLogger

_VALID_COMMANDS = (
    "play, pause, resume, skip, seek, queue, like, unlike, follow, unfollow, "
    "save, unsave, add...to, remove...from, create playlist, delete playlist, "
    "search, now playing, get queue, get devices, library, info, history, recommend"
)

_DEFAULT_CONFIG_DIR = Path.home() / ".config" / "clautify"
_DEFAULT_SESSION_PATH = _DEFAULT_CONFIG_DIR / "session.json"

__all__ = ["SpotifySession", "parse", "DSLError"]


class SpotifySession:
    """Session-based DSL entry point for Spotify commands.

    Holds a Login and lazily initializes SpotAPI classes as needed.
    Player (heavyweight — WebSocket + threads) is only created on
    first playback command.
    """

    def __init__(self, login: Login, eager: bool = True):
        self._executor = SpotifyExecutor(login, eager=eager)

    @classmethod
    def setup(
        cls,
        sp_dc: str,
        *,
        identifier: str = "default",
        path: Union[str, Path, None] = None,
    ) -> Path:
        """Save an sp_dc cookie to disk for future auto-loading.

        Get sp_dc from browser dev tools: Application → Cookies → sp_dc.
        Only needs to be called once (cookie typically lasts ~1 year).
        """
        if not sp_dc:
            raise DSLError("sp_dc cookie value is required")
        dest = Path(path) if path else _DEFAULT_SESSION_PATH
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = {"identifier": identifier, "cookies": {"sp_dc": sp_dc}}
        dest.write_text(json.dumps(data, indent=2))
        return dest

    @classmethod
    def from_config(
        cls,
        path: Union[str, Path, None] = None,
        *,
        eager: bool = True,
    ) -> "SpotifySession":
        """Create a session from a saved config file.

        Loads cookies from ~/.config/clautify/session.json (or custom path).
        Call SpotifySession.setup() first if no config exists.
        """
        src = Path(path) if path else _DEFAULT_SESSION_PATH
        if not src.exists():
            raise DSLError(f"No session file found at {src}. Run SpotifySession.setup('your_sp_dc_cookie') first.")
        raw = json.loads(src.read_text())
        dump = {
            "identifier": raw.get("identifier", "default"),
            "password": "",
            "cookies": raw["cookies"],
        }
        cfg = Config(logger=NoopLogger())
        login = Login.from_cookies(dump, cfg)
        return cls(login, eager=eager)

    def health_check(self) -> Dict[str, Any]:
        """Verify Spotify session is valid by fetching an access token.

        Lightweight — single HTTP GET to the token endpoint, no Player/WebSocket init.
        Returns {"status": "ok", "authenticated": True} on success,
        or {"status": "error", "authenticated": False, "error": "..."} on failure.
        """
        try:
            self._executor._login.client._get_auth_vars()
            return {"status": "ok", "authenticated": True}
        except Exception as e:
            return {"status": "error", "authenticated": False, "error": str(e)}

    def run(self, command: str) -> Dict[str, Any]:
        """Parse and execute a DSL command string.

        Returns a result dict with a "status" key ("ok" on success)
        plus command-specific data.

        Raises DSLError on parse or execution failure.
        """
        try:
            parsed = parse(command)
        except UnexpectedInput as e:
            raise DSLError(f"Invalid command: '{command}'. Valid commands: {_VALID_COMMANDS}") from e
        except Exception as e:
            raise DSLError(f"Parse error: {e}") from e

        return self._executor.execute(parsed)

    def close(self) -> None:
        """Clean up resources (WebSocket, threads)."""
        self._executor.close()
