"""Spotify DSL executor — dispatches parsed command dicts to SpotAPI classes."""

from typing import Any, Dict, Optional

from clautify.album import PublicAlbum
from clautify.artist import Artist
from clautify.login import Login
from clautify.player import Player
from clautify.playlist import PrivatePlaylist
from clautify.song import Song


class DSLError(Exception):
    """Raised when a DSL command fails."""

    def __init__(self, message: str, command: Optional[Dict[str, Any]] = None):
        self.command = command
        super().__init__(message)


def _extract_id(uri_or_name: str, kind: str = "track") -> str:
    """Extract the bare ID from a Spotify URI, or return as-is."""
    prefix = f"spotify:{kind}:"
    return uri_or_name[len(prefix) :] if uri_or_name.startswith(prefix) else uri_or_name


def _is_uri(target: str) -> bool:
    return target.startswith("spotify:")


def _uri_kind(uri: str) -> str:
    """Get the entity type from a Spotify URI."""
    parts = uri.split(":")
    return parts[1] if len(parts) >= 3 else "track"


# --- dispatch tables for simple actions ---

# action -> (executor_property, method_name, uri_kind)
_SIMPLE_TARGET_ACTIONS = {
    "like": ("song", "like_song", "track"),
    "unlike": ("song", "unlike_song", "track"),
    "follow": ("artist", "follow", "artist"),
    "unfollow": ("artist", "unfollow", "artist"),
}

# action -> playlist method name
_PLAYLIST_ACTIONS = {
    "save": "add_to_library",
    "unsave": "remove_from_library",
    "playlist_delete": "delete_playlist",
}


class SpotifyExecutor:
    """Dispatches parsed DSL command dicts to SpotAPI class methods.

    Lazily initializes heavy resources (Player requires WebSocket + threads).
    """

    def __init__(self, login: Login, eager: bool = True):
        self._login = login
        self._player: Optional[Player] = None
        self._song: Optional[Song] = None
        self._artist: Optional[Artist] = None
        if eager:
            _ = self.player

    # --- lazy properties ---

    @property
    def player(self) -> Player:
        if self._player is None:
            self._player = Player(self._login)
        return self._player

    @property
    def song(self) -> Song:
        if self._song is None:
            sentinel = PrivatePlaylist(self._login, "__sentinel__")
            self._song = Song(playlist=sentinel)
        return self._song

    @property
    def artist(self) -> Artist:
        if self._artist is None:
            self._artist = Artist(login=self._login)
        return self._artist

    def close(self) -> None:
        """Clean up resources (WebSocket, threads) if Player was created."""
        if self._player is not None:
            try:
                self._player.ws.close()
            except Exception:
                pass

    def _playlist_for(self, target: str) -> PrivatePlaylist:
        """Fresh PrivatePlaylist per call (instance methods use self.playlist_id)."""
        return PrivatePlaylist(self._login, _extract_id(target, "playlist"))

    def _resolve_device_id(self, name: str) -> str:
        """Resolve a friendly device name to a device ID (case-insensitive)."""
        devices = self.player.device_ids
        name_lower = name.lower()
        for device in devices.devices.values():
            if device.name.lower() == name_lower:
                return device.device_id
        available = [d.name for d in devices.devices.values()]
        raise DSLError(f"Device '{name}' not found. Available: {available}")

    def _resolve_track_uri(self, name: str, cmd: Dict[str, Any]) -> str:
        """Search for a track by name, return the top result's URI."""
        results = self.song.query_songs(name, limit=1)
        try:
            items = results["data"]["searchV2"]["tracksV2"]["items"]
            if not items:
                raise DSLError(f"No results for '{name}'", command=cmd)
            return items[0]["item"]["data"]["uri"]
        except (KeyError, IndexError) as e:
            raise DSLError(f"Could not extract track from search results: {e}", command=cmd)

    # --- main dispatch ---

    def execute(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a parsed command dict and return the result."""
        try:
            if "action" in cmd:
                return self._dispatch_action(cmd)
            elif "query" in cmd:
                return self._dispatch_query(cmd)
            else:
                raise DSLError("Invalid command: no action or query key", command=cmd)
        except DSLError:
            raise
        except Exception as e:
            raise DSLError(f"{type(e).__name__}: {e}", command=cmd) from e

    # --- action dispatch ---

    def _dispatch_action(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        action = cmd["action"]

        # Table-driven: target → service.method(id)
        if action in _SIMPLE_TARGET_ACTIONS:
            service_attr, method, kind = _SIMPLE_TARGET_ACTIONS[action]
            target = cmd["target"]
            getattr(getattr(self, service_attr), method)(_extract_id(target, kind))
            result = {"status": "ok", "action": action, "target": target}

        # Table-driven: target → playlist.method()
        elif action in _PLAYLIST_ACTIONS:
            target = cmd["target"]
            getattr(self._playlist_for(target), _PLAYLIST_ACTIONS[action])()
            result = {"status": "ok", "action": action, "target": target}

        # Simple player commands
        elif action in ("pause", "resume"):
            getattr(self.player, action)()
            result = {"status": "ok", "action": action}

        # Standalone state modifiers
        elif action == "set":
            result = {"status": "ok", "action": "set"}
            for k in ("volume", "volume_rel", "mode", "device"):
                if k in cmd:
                    result[k] = cmd[k]

        # Complex actions with custom logic
        else:
            handler = getattr(self, f"_action_{action}", None)
            if handler is None:
                raise DSLError(f"Unknown action: {action}", command=cmd)
            result = handler(cmd)

        self._apply_state_modifiers(cmd)
        return result

    def _apply_state_modifiers(self, cmd: Dict[str, Any]) -> None:
        if "volume" in cmd:
            vol = cmd["volume"]
            if not (0 <= vol <= 100):
                raise DSLError(f"Volume must be 0-100, got {vol}")
            # Normalize to 0-1.0 for Player API
            self.player.set_volume(vol if vol <= 1 else vol / 100)
        if "volume_rel" in cmd:
            delta = cmd["volume_rel"]  # percentage points, e.g. +10 or -5
            devices = self.player.device_ids
            dev = devices.devices.get(self.player.active_id)
            if dev is None:
                raise DSLError("Cannot determine current volume for relative adjustment")
            current = dev.volume / 65535  # 0.0 to 1.0
            new_vol = max(0.0, min(1.0, current + delta / 100))
            self.player.set_volume(new_vol)
        if "mode" in cmd:
            mode = cmd["mode"]
            self.player.set_shuffle(mode == "shuffle")
            self.player.repeat_track(mode == "repeat")
        if "device" in cmd:
            device_id = self._resolve_device_id(cmd["device"])
            self.player.transfer_player(self.player.device_id, device_id)

    # --- complex action handlers ---

    def _action_play(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        target = cmd["target"]
        context = cmd.get("context")

        # Resolve target if it's a quoted string
        if _is_uri(target):
            track_uri = target
        else:
            track_uri = self._resolve_track_uri(target, cmd)

        # With context — use play_track (requires URI context)
        if context:
            if not _is_uri(context):
                raise DSLError(
                    'play with "in" context requires a playlist URI, e.g. play "song" in spotify:playlist:abc',
                    command=cmd,
                )
            self.player.play_track(track_uri, context)
            result = {"status": "ok", "action": "play", "target": target, "context": context}
        else:
            # No context — queue + skip
            self.player.add_to_queue(track_uri)
            self.player.skip_next()
            result = {"status": "ok", "action": "play", "target": target}

        if track_uri != target:
            result["resolved_uri"] = track_uri
        return result

    def _action_skip(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        n = cmd.get("n", 1)
        fn = self.player.skip_next if n >= 0 else self.player.skip_prev
        for _ in range(abs(n)):
            fn()
        return {"status": "ok", "action": "skip", "n": n}

    def _action_seek(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        position_ms = int(cmd["position_ms"])
        self.player.seek_to(position_ms)
        return {"status": "ok", "action": "seek", "position_ms": position_ms}

    def _action_queue(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        target = cmd["target"]
        uri = target if _is_uri(target) else self._resolve_track_uri(target, cmd)
        self.player.add_to_queue(uri)
        return {"status": "ok", "action": "queue", "target": uri}

    def _action_playlist_add(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        track, playlist = cmd["track"], cmd["playlist"]
        pl = PrivatePlaylist(self._login, _extract_id(playlist, "playlist"))
        Song(playlist=pl).add_song_to_playlist(_extract_id(track, "track"))
        return {"status": "ok", "action": "playlist_add", "track": track, "playlist": playlist}

    def _action_playlist_remove(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        track, playlist = cmd["track"], cmd["playlist"]
        pl = PrivatePlaylist(self._login, _extract_id(playlist, "playlist"))
        Song(playlist=pl).remove_song_from_playlist(song_id=_extract_id(track, "track"))
        return {"status": "ok", "action": "playlist_remove", "track": track, "playlist": playlist}

    def _action_playlist_create(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        name = cmd["name"]
        playlist_id = PrivatePlaylist(self._login).create_playlist(name)
        return {
            "status": "ok",
            "action": "playlist_create",
            "name": name,
            "playlist_id": playlist_id,
        }

    # --- query dispatch ---

    def _dispatch_query(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        query = cmd["query"]
        handler = getattr(self, f"_query_{query}", None)
        if handler is None:
            raise DSLError(f"Unknown query: {query}", command=cmd)
        return handler(cmd)

    def _query_search(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        term = cmd["term"]
        type_ = cmd.get("type")
        limit = cmd.get("limit", 10)
        offset = cmd.get("offset", 0)

        if type_ == "artists":
            results = self.artist.query_artists(term, limit=limit, offset=offset)
        else:
            # searchDesktop returns all types (tracks, albums, playlists)
            results = self.song.query_songs(term, limit=limit, offset=offset)

        return {"status": "ok", "query": "search", "term": term, "type": type_, "data": results}

    def _query_now_playing(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "ok", "query": "now_playing", "data": self.player.state}

    def _query_get_queue(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "ok", "query": "get_queue", "data": self.player.next_songs_in_queue}

    def _query_get_devices(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "ok", "query": "get_devices", "data": self.player.device_ids}

    def _query_library(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        # Note: underlying get_library() does not support offset — pagination
        # must be handled by the caller. Type filtering is left to the caller
        # since the response structure varies by Spotify API version.
        data = PrivatePlaylist(self._login).get_library(cmd.get("limit", 50))
        return {"status": "ok", "query": "library", "type": cmd.get("type"), "data": data}

    def _query_info(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        target = cmd["target"]
        if not _is_uri(target):
            raise DSLError(
                "info requires a Spotify URI (e.g. spotify:track:abc). Use search to find URIs first.",
                command=cmd,
            )

        kind = _uri_kind(target)
        bare_id = _extract_id(target, kind)

        if kind == "track":
            data = self.song.get_track_info(bare_id)
        elif kind == "artist":
            data = self.artist.get_artist(bare_id)
        elif kind == "album":
            data = PublicAlbum(bare_id).get_album_info()
        elif kind == "playlist":
            from clautify.playlist import PublicPlaylist

            data = PublicPlaylist(bare_id).get_playlist_info()
        else:
            raise DSLError(f"Cannot get info for URI type: {kind}", command=cmd)

        return {"status": "ok", "query": "info", "target": target, "data": data}

    def _query_history(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        songs = self.player.last_songs_played
        limit = cmd.get("limit")
        return {"status": "ok", "query": "history", "data": songs[:limit] if limit else songs}

    def _query_recommend(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        target, n = cmd["target"], cmd.get("n", 20)
        if not _is_uri(target) or _uri_kind(target) != "playlist":
            raise DSLError(
                f"recommend requires a playlist URI (e.g. spotify:playlist:abc), got '{target}'",
                command=cmd,
            )
        data = self._playlist_for(target).recommended_songs(num_songs=n)
        return {"status": "ok", "query": "recommend", "target": target, "n": n, "data": data}
