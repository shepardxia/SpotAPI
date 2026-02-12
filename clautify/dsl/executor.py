"""Spotify DSL executor — dispatches parsed command dicts to SpotAPI classes."""

from pathlib import Path
from typing import Any, Dict, Optional

from clautify.album import PublicAlbum
from clautify.artist import Artist
from clautify.exceptions import WebSocketError
from clautify.login import Login
from clautify.player import Player
from clautify.playlist import PrivatePlaylist
from clautify.song import Song
from clautify.types.data import Metadata

from .cache import NameCache


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

_LIBRARY_FILTERS = {
    "playlists": ["Playlists"],
    "artists": ["Artists"],
    "albums": ["Albums"],
}

_SEARCH_SECTION_PATH = {
    "tracks": ("data", "searchV2", "tracksV2", "items"),
    "albums": ("data", "searchV2", "albumsV2", "items"),
    "playlists": ("data", "searchV2", "playlists", "items"),
}


class SpotifyExecutor:
    """Dispatches parsed DSL command dicts to SpotAPI class methods.

    Lazily initializes heavy resources (Player requires WebSocket + threads).
    """

    def __init__(self, login: Login, eager: bool = True, cache_path: Optional[Path] = None, max_volume: float = 1.0):
        self._login = login
        self._player: Optional[Player] = None
        self._song: Optional[Song] = None
        self._artist: Optional[Artist] = None
        self._cache = NameCache(path=cache_path)
        self._max_volume = max(0.0, min(1.0, max_volume))
        if eager:
            _ = self.player  # warm Player; if it fails, first command will retry

    # --- lazy properties ---

    @property
    def player(self) -> Player:
        if self._player is None:
            self._player = Player(self._login)
        return self._player

    def _reset_player(self) -> None:
        """Tear down a stale Player so the next access creates a fresh one."""
        if self._player is not None:
            try:
                self._player.ws.close()
            except Exception:
                pass
            self._player = None

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

    def _resolve_uri(self, kind: str, name: str, cmd: Dict[str, Any]) -> str:
        """Resolve a name to URI via cache. Raises DSLError if not cached."""
        uri = self._cache.resolve(kind, name)
        if uri is None:
            raise DSLError(
                f'"{name}" not found. Use search first to find it.',
                command=cmd,
            )
        return uri

    # --- main dispatch ---

    def execute(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a parsed command dict and return the result."""
        try:
            return self._execute_once(cmd)
        except (WebSocketError, DSLError) as first:
            # Only retry if WebSocketError — either raised directly or chained as __cause__ of DSLError
            inner = first.__cause__ if isinstance(first, DSLError) else first
            if not isinstance(inner, WebSocketError) and not isinstance(first, WebSocketError):
                raise
            self._reset_player()
            try:
                return self._execute_once(cmd)
            except DSLError:
                raise
            except Exception as e:
                raise DSLError(f"{type(e).__name__}: {e}", command=cmd) from e

    def _execute_once(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if "action" in cmd:
                result = self._dispatch_action(cmd)
            elif "query" in cmd:
                result = self._dispatch_query(cmd)
            else:
                raise DSLError("Invalid command: no action or query key", command=cmd)
            self._cache.save()
            return result
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

        # Annotate effective volume after max_volume capping
        if "volume" in cmd and "volume" in result:
            result["volume"] = min(cmd["volume"], self._max_volume * 100)

        return result

    def _apply_state_modifiers(self, cmd: Dict[str, Any]) -> None:
        if "volume" in cmd:
            vol = cmd["volume"]
            if not (0 <= vol <= 100):
                raise DSLError(f"Volume must be 0-100, got {vol}")
            normalized = min(vol / 100, self._max_volume)
            self.player.set_volume(normalized)
        if "volume_rel" in cmd:
            delta = cmd["volume_rel"]  # percentage points, e.g. +10 or -5
            devices = self.player.device_ids
            dev = devices.devices.get(self.player.active_id)
            if dev is None:
                raise DSLError("Cannot determine current volume for relative adjustment")
            current = dev.volume / 65535  # 0.0 to 1.0
            new_vol = max(0.0, min(self._max_volume, current + delta / 100))
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
        kind = cmd.get("kind", "track")

        if _is_uri(target):
            uri = target
            kind = _uri_kind(target)
        else:
            uri = self._resolve_uri(kind, target, cmd)

        if kind in ("album", "playlist"):
            self.player.play_context(uri)
            result = {"status": "ok", "action": "play", "kind": kind, "target": target}
        elif context:
            # With context — use play_track (requires URI context)
            if not _is_uri(context):
                raise DSLError(
                    'play with "in" context requires a playlist URI, e.g. play "song" in spotify:playlist:abc',
                    command=cmd,
                )
            self.player.play_track(uri, context)
            result = {"status": "ok", "action": "play", "kind": kind, "target": target, "context": context}
        else:
            # No context — queue + skip
            self.player.add_to_queue(uri)
            self.player.skip_next()
            result = {"status": "ok", "action": "play", "kind": kind, "target": target}

        if uri != target:
            result["resolved_uri"] = uri
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
        uri = target if _is_uri(target) else self._resolve_uri("track", target, cmd)
        self.player.add_to_queue(uri)
        return {"status": "ok", "action": "queue", "target": target}

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
        terms = cmd["terms"]
        type_ = cmd.get("type")
        limit = cmd.get("limit", 10)
        offset = cmd.get("offset", 0)

        if not type_:
            type_ = "tracks"

        all_results = []
        for term in terms:
            if type_ == "artists":
                raw = self.artist.query_artists(term, limit=limit, offset=offset)
                self._cache_search_artists(raw)
                # Extract items for uniform flat list
                try:
                    items = raw["data"]["searchV2"]["artists"]["items"]
                    all_results.extend(items)
                except (KeyError, TypeError):
                    pass
            else:
                raw = self.song.query_songs(term, limit=limit, offset=offset)
                results = self._extract_search_section(raw, type_)
                self._cache_search_results(results, type_)
                if isinstance(results, list):
                    all_results.extend(results)

        return {"status": "ok", "query": "search", "terms": terms, "type": type_, "data": all_results}

    def _query_now_playing(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        state = self.player.state
        # Enrich current track metadata (artist name, etc.)
        if hasattr(state, "track") and state.track:
            self._enrich_tracks([state.track])
        return {"status": "ok", "query": "now_playing", "data": state}

    def _query_get_queue(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        tracks = self.player.next_songs_in_queue
        limit = cmd.get("limit", 10)
        if isinstance(tracks, list):
            self._enrich_tracks(tracks[:limit])
        return {"status": "ok", "query": "get_queue", "data": tracks, "limit": limit}

    def _query_get_devices(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "ok", "query": "get_devices", "data": self.player.device_ids}

    def _query_library(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        type_ = cmd.get("type")
        filters = _LIBRARY_FILTERS.get(type_, [])
        limit = cmd.get("limit", 50)
        offset = cmd.get("offset", 0)
        data = PrivatePlaylist(self._login).get_library(limit, offset=offset, filters=filters)
        self._cache_library(data)
        return {"status": "ok", "query": "library", "type": type_, "data": data}

    def _query_info(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        target = cmd["target"]

        # Resolve names via cache (same search-first pattern as play/queue)
        if not _is_uri(target):
            for kind in ("artist", "track", "album", "playlist"):
                uri = self._cache.resolve(kind, target)
                if uri is not None:
                    target = uri
                    break
            else:
                raise DSLError(
                    f'"{target}" not found. Use search first to find it.',
                    command=cmd,
                )

        kind = _uri_kind(target)
        bare_id = _extract_id(target, kind)
        limit = cmd.get("limit", 25)
        offset = cmd.get("offset", 0)

        if kind == "track":
            data = self.song.get_track_info(bare_id)
        elif kind == "artist":
            data = self.artist.get_artist(bare_id)
        elif kind == "album":
            data = PublicAlbum(bare_id).get_album_info(limit=limit, offset=offset)
        elif kind == "playlist":
            from clautify.playlist import PublicPlaylist

            data = PublicPlaylist(bare_id).get_playlist_info(limit=limit, offset=offset)
        else:
            raise DSLError(f"Cannot get info for URI type: {kind}", command=cmd)

        self._cache_info(target, kind, data)
        return {"status": "ok", "query": "info", "target": target, "data": data}

    def _query_history(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        tracks = self.player.last_songs_played
        limit = cmd.get("limit", 10)
        if isinstance(tracks, list):
            self._enrich_tracks(tracks[:limit])
        return {"status": "ok", "query": "history", "data": tracks, "limit": limit}

    def _query_recommend(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        target, n = cmd["target"], cmd.get("n", 20)
        if not _is_uri(target) or _uri_kind(target) != "playlist":
            raise DSLError(
                f"recommend requires a playlist URI (e.g. spotify:playlist:abc), got '{target}'",
                command=cmd,
            )
        data = self._playlist_for(target).recommended_songs(num_songs=n)
        self._cache_recommend(data)
        return {"status": "ok", "query": "recommend", "target": target, "n": n, "data": data}

    # --- cache helpers ---

    def _extract_search_section(self, raw: Dict[str, Any], type_: str) -> Any:
        """Extract a specific section from searchDesktop results."""
        path = _SEARCH_SECTION_PATH.get(type_)
        if not path:
            return raw
        result = raw
        for key in path:
            if isinstance(result, dict):
                result = result.get(key, {})
            else:
                return raw
        return result

    def _cache_search_results(self, items: Any, type_: str) -> None:
        """Cache name->URI pairs from search results, including embedded artists."""
        if not isinstance(items, list):
            return
        kind_map = {"tracks": "track", "albums": "album", "playlists": "playlist"}
        kind = kind_map.get(type_, type_.rstrip("s"))
        for item in items:
            try:
                data = item.get("item", {}).get("data", {}) if type_ == "tracks" else item.get("data", {})
                name = data.get("name")
                uri = data.get("uri")
                if name and uri:
                    self._cache.add(kind, name, uri)
                # Also cache embedded artist info
                artists = data.get("artists", {}).get("items", [])
                for a in artists:
                    a_name = a.get("profile", {}).get("name")
                    a_uri = a.get("uri")
                    if a_name and a_uri:
                        self._cache.add("artist", a_name, a_uri)
            except (AttributeError, TypeError):
                continue

    def _cache_search_artists(self, results: Dict[str, Any]) -> None:
        """Cache artist names from searchArtists results."""
        try:
            items = results.get("data", {}).get("searchV2", {}).get("artists", {}).get("items", [])
            for item in items:
                data = item.get("data", {})
                name = data.get("profile", {}).get("name")
                uri = data.get("uri")
                if name and uri:
                    self._cache.add("artist", name, uri)
        except (AttributeError, TypeError):
            pass

    def _cache_library(self, data: Any) -> None:
        """Cache names from library results."""
        try:
            items = data.get("data", {}).get("me", {}).get("libraryV3", {}).get("items", [])
            for item in items:
                item_data = item.get("item", {}).get("data", {})
                name = item_data.get("name")
                uri = item_data.get("uri")
                typename = item_data.get("__typename", "")
                if name and uri:
                    if "Playlist" in typename:
                        self._cache.add("playlist", name, uri)
                    elif "Album" in typename:
                        self._cache.add("album", name, uri)
                    elif "Artist" in typename:
                        self._cache.add("artist", name, uri)
        except (AttributeError, TypeError):
            pass

    def _cache_info(self, target: str, kind: str, data: Any) -> None:
        """Cache entity name from info results."""
        try:
            if kind == "track":
                track_data = data.get("data", {}).get("trackUnion", {})
                name = track_data.get("name")
                if name:
                    self._cache.add("track", name, target)
            elif kind == "artist":
                artist_data = data.get("data", {}).get("artistUnion", {})
                name = artist_data.get("profile", {}).get("name")
                if name:
                    self._cache.add("artist", name, target)
            elif kind == "album":
                album_data = data.get("data", {}).get("albumUnion", {})
                name = album_data.get("name")
                if name:
                    self._cache.add("album", name, target)
            elif kind == "playlist":
                pl_data = data.get("data", {}).get("playlistV2", {})
                name = pl_data.get("name")
                if name:
                    self._cache.add("playlist", name, target)
        except (AttributeError, TypeError):
            pass

    def _enrich_tracks(self, tracks: list) -> None:
        """Resolve null-metadata tracks via cache reverse lookup or getTrack API."""
        for track in tracks:
            if not hasattr(track, "uri") or not track.uri:
                continue
            if hasattr(track, "metadata") and track.metadata and track.metadata.title:
                continue  # already has metadata
            # Try cache first
            cached_name = self._cache.name_for_uri(track.uri)
            if cached_name:
                if not hasattr(track, "metadata") or track.metadata is None:
                    track.metadata = Metadata(title=cached_name)
                else:
                    track.metadata.title = cached_name
                continue
            # Fetch from API
            try:
                track_id = track.uri.split(":")[-1]
                info = self.song.get_track_info(track_id)
                track_data = info.get("data", {}).get("trackUnion", {})
                name = track_data.get("name")
                if not name:
                    continue
                album_name = track_data.get("albumOfTrack", {}).get("name")
                artists = track_data.get("firstArtist", {}).get("items", [])
                artist_uri = artists[0].get("uri") if artists else None
                artist_name = artists[0].get("profile", {}).get("name") if artists else None
                track.metadata = Metadata(
                    title=name,
                    album_title=album_name,
                    artist_uri=artist_uri,
                )
                self._cache.add("track", name, track.uri)
                if artist_name and artist_uri:
                    self._cache.add("artist", artist_name, artist_uri)
            except Exception:
                continue

    def _cache_recommend(self, data: Any) -> None:
        """Cache track names from recommendations."""
        try:
            tracks = data.get("recommendedTracks", [])
            for t in tracks:
                name = t.get("name")
                uri = t.get("originalId")
                if name and uri:
                    self._cache.add("track", name, uri)
        except (AttributeError, TypeError):
            pass
