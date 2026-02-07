"""Tests for the DSL executor — mocked SpotAPI classes, no network calls."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from clautify.dsl.executor import SpotifyExecutor, DSLError


@pytest.fixture
def login():
    return MagicMock()


@pytest.fixture
def executor(login):
    return SpotifyExecutor(login, eager=False)


# ── Lazy Initialization ──────────────────────────────────────────


class TestLazyInit:
    def test_player_not_created_on_init(self, executor):
        assert executor._player is None

    def test_song_not_created_on_init(self, executor):
        assert executor._song is None

    def test_artist_not_created_on_init(self, executor):
        assert executor._artist is None

    @patch("clautify.dsl.executor.Player")
    def test_player_created_on_playback(self, MockPlayer, executor):
        mock_player = MagicMock()
        MockPlayer.return_value = mock_player

        executor.execute({"action": "pause"})

        MockPlayer.assert_called_once_with(executor._login)
        assert executor._player is mock_player

    @patch("clautify.dsl.executor.Player")
    def test_player_created_once(self, MockPlayer, executor):
        mock_player = MagicMock()
        MockPlayer.return_value = mock_player

        executor.execute({"action": "pause"})
        executor.execute({"action": "resume"})

        MockPlayer.assert_called_once()

    @patch("clautify.dsl.executor.Song")
    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_search_does_not_create_player(self, MockPP, MockSong, executor):
        mock_song = MagicMock()
        mock_song.query_songs.return_value = {"data": {"searchV2": {"tracksV2": {"items": []}}}}
        MockSong.return_value = mock_song

        executor.execute({"query": "search", "term": "jazz"})

        assert executor._player is None


# ── Action Dispatch ───────────────────────────────────────────────


class TestActions:
    @patch("clautify.dsl.executor.Player")
    def test_pause(self, MockPlayer, executor):
        mock_player = MagicMock()
        MockPlayer.return_value = mock_player

        result = executor.execute({"action": "pause"})

        mock_player.pause.assert_called_once()
        assert result["status"] == "ok"
        assert result["action"] == "pause"

    @patch("clautify.dsl.executor.Player")
    def test_resume(self, MockPlayer, executor):
        mock_player = MagicMock()
        MockPlayer.return_value = mock_player

        result = executor.execute({"action": "resume"})

        mock_player.resume.assert_called_once()
        assert result["status"] == "ok"

    @patch("clautify.dsl.executor.Player")
    def test_skip_forward(self, MockPlayer, executor):
        mock_player = MagicMock()
        MockPlayer.return_value = mock_player

        result = executor.execute({"action": "skip", "n": 3})

        assert mock_player.skip_next.call_count == 3
        assert result["n"] == 3

    @patch("clautify.dsl.executor.Player")
    def test_skip_backward(self, MockPlayer, executor):
        mock_player = MagicMock()
        MockPlayer.return_value = mock_player

        result = executor.execute({"action": "skip", "n": -2})

        assert mock_player.skip_prev.call_count == 2

    @patch("clautify.dsl.executor.Player")
    def test_seek(self, MockPlayer, executor):
        mock_player = MagicMock()
        MockPlayer.return_value = mock_player

        result = executor.execute({"action": "seek", "position_ms": 30000})

        mock_player.seek_to.assert_called_once_with(30000)

    @patch("clautify.dsl.executor.Player")
    def test_queue_uri(self, MockPlayer, executor):
        mock_player = MagicMock()
        MockPlayer.return_value = mock_player

        result = executor.execute({"action": "queue", "target": "spotify:track:abc"})

        mock_player.add_to_queue.assert_called_once_with("spotify:track:abc")

    @patch("clautify.dsl.executor.Song")
    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_like(self, MockPP, MockSong, executor):
        mock_song = MagicMock()
        MockSong.return_value = mock_song

        result = executor.execute({"action": "like", "target": "spotify:track:abc123"})

        mock_song.like_song.assert_called_once_with("abc123")
        assert result["status"] == "ok"

    @patch("clautify.dsl.executor.Song")
    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_unlike(self, MockPP, MockSong, executor):
        mock_song = MagicMock()
        MockSong.return_value = mock_song

        result = executor.execute({"action": "unlike", "target": "spotify:track:abc123"})

        mock_song.unlike_song.assert_called_once_with("abc123")

    @patch("clautify.dsl.executor.Artist")
    def test_follow(self, MockArtist, executor):
        mock_artist = MagicMock()
        MockArtist.return_value = mock_artist

        result = executor.execute({"action": "follow", "target": "spotify:artist:xyz"})

        mock_artist.follow.assert_called_once_with("xyz")

    @patch("clautify.dsl.executor.Artist")
    def test_unfollow(self, MockArtist, executor):
        mock_artist = MagicMock()
        MockArtist.return_value = mock_artist

        result = executor.execute({"action": "unfollow", "target": "spotify:artist:xyz"})

        mock_artist.unfollow.assert_called_once_with("xyz")


# ── Playlist Actions ──────────────────────────────────────────────


class TestPlaylistActions:
    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_save(self, MockPP, executor):
        mock_pp = MagicMock()
        MockPP.return_value = mock_pp

        result = executor.execute({"action": "save", "target": "spotify:playlist:abc123"})

        MockPP.assert_called_with(executor._login, "abc123")
        mock_pp.add_to_library.assert_called_once()

    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_unsave(self, MockPP, executor):
        mock_pp = MagicMock()
        MockPP.return_value = mock_pp

        result = executor.execute({"action": "unsave", "target": "spotify:playlist:abc123"})

        mock_pp.remove_from_library.assert_called_once()

    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_delete_playlist(self, MockPP, executor):
        mock_pp = MagicMock()
        MockPP.return_value = mock_pp

        result = executor.execute({"action": "playlist_delete", "target": "spotify:playlist:abc"})

        mock_pp.delete_playlist.assert_called_once()

    @patch("clautify.dsl.executor.Song")
    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_playlist_add(self, MockPP, MockSong, executor):
        mock_song = MagicMock()
        MockSong.return_value = mock_song

        result = executor.execute({
            "action": "playlist_add",
            "track": "spotify:track:abc",
            "playlist": "spotify:playlist:def",
        })

        mock_song.add_song_to_playlist.assert_called_once_with("abc")

    @patch("clautify.dsl.executor.Song")
    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_playlist_remove(self, MockPP, MockSong, executor):
        mock_song = MagicMock()
        MockSong.return_value = mock_song

        result = executor.execute({
            "action": "playlist_remove",
            "track": "spotify:track:abc",
            "playlist": "spotify:playlist:def",
        })

        mock_song.remove_song_from_playlist.assert_called_once_with(song_id="abc")

    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_create_playlist(self, MockPP, executor):
        mock_pp = MagicMock()
        mock_pp.create_playlist.return_value = "new_playlist_id"
        MockPP.return_value = mock_pp

        result = executor.execute({"action": "playlist_create", "name": "Road Trip"})

        mock_pp.create_playlist.assert_called_once_with("Road Trip")
        assert result["playlist_id"] == "new_playlist_id"


# ── State Modifiers ───────────────────────────────────────────────


class TestStateModifiers:
    @patch("clautify.dsl.executor.Player")
    def test_volume_after_action(self, MockPlayer, executor):
        mock_player = MagicMock()
        MockPlayer.return_value = mock_player

        executor.execute({"action": "pause", "volume": 70})

        mock_player.pause.assert_called_once()
        mock_player.set_volume.assert_called_once_with(0.7)

    @patch("clautify.dsl.executor.Player")
    def test_mode_shuffle(self, MockPlayer, executor):
        mock_player = MagicMock()
        MockPlayer.return_value = mock_player

        executor.execute({"action": "set", "mode": "shuffle"})

        mock_player.set_shuffle.assert_called_once_with(True)
        mock_player.repeat_track.assert_called_once_with(False)

    @patch("clautify.dsl.executor.Player")
    def test_mode_repeat(self, MockPlayer, executor):
        mock_player = MagicMock()
        MockPlayer.return_value = mock_player

        executor.execute({"action": "set", "mode": "repeat"})

        mock_player.set_shuffle.assert_called_once_with(False)
        mock_player.repeat_track.assert_called_once_with(True)

    @patch("clautify.dsl.executor.Player")
    def test_mode_normal(self, MockPlayer, executor):
        mock_player = MagicMock()
        MockPlayer.return_value = mock_player

        executor.execute({"action": "set", "mode": "normal"})

        mock_player.set_shuffle.assert_called_once_with(False)
        mock_player.repeat_track.assert_called_once_with(False)

    @patch("clautify.dsl.executor.Player")
    def test_device_transfer(self, MockPlayer, executor):
        mock_device = MagicMock()
        mock_device.name = "Living Room"
        mock_device.device_id = "abc123hex"
        mock_devices = MagicMock()
        mock_devices.devices = {"0": mock_device}

        mock_player = MagicMock()
        mock_player.device_id = "origin_device"
        mock_player.device_ids = mock_devices
        MockPlayer.return_value = mock_player

        executor.execute({"action": "set", "device": "Living Room"})

        mock_player.transfer_player.assert_called_once_with("origin_device", "abc123hex")

    @patch("clautify.dsl.executor.Player")
    def test_standalone_volume(self, MockPlayer, executor):
        mock_player = MagicMock()
        MockPlayer.return_value = mock_player

        result = executor.execute({"action": "set", "volume": 50})

        mock_player.set_volume.assert_called_once_with(0.5)
        assert result["volume"] == 50


# ── Compound Operations ──────────────────────────────────────────


class TestCompoundOps:
    @patch("clautify.dsl.executor.Player")
    @patch("clautify.dsl.executor.Song")
    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_play_string_searches_and_plays(self, MockPP, MockSong, MockPlayer, executor):
        mock_song = MagicMock()
        mock_song.query_songs.return_value = {
            "data": {
                "searchV2": {
                    "tracksV2": {
                        "items": [
                            {"item": {"data": {"uri": "spotify:track:found123"}}}
                        ]
                    }
                }
            }
        }
        MockSong.return_value = mock_song

        mock_player = MagicMock()
        MockPlayer.return_value = mock_player

        result = executor.execute({"action": "play", "target": "jazz"})

        mock_song.query_songs.assert_called_once_with("jazz", limit=1)
        mock_player.add_to_queue.assert_called_once_with("spotify:track:found123")
        mock_player.skip_next.assert_called_once()
        assert result["resolved_uri"] == "spotify:track:found123"

    @patch("clautify.dsl.executor.Player")
    @patch("clautify.dsl.executor.Song")
    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_play_string_no_results(self, MockPP, MockSong, MockPlayer, executor):
        mock_song = MagicMock()
        mock_song.query_songs.return_value = {
            "data": {"searchV2": {"tracksV2": {"items": []}}}
        }
        MockSong.return_value = mock_song
        MockPlayer.return_value = MagicMock()

        with pytest.raises(DSLError, match="No results"):
            executor.execute({"action": "play", "target": "nonexistent song xyz"})

    @patch("clautify.dsl.executor.Player")
    def test_play_uri_no_context(self, MockPlayer, executor):
        mock_player = MagicMock()
        MockPlayer.return_value = mock_player

        result = executor.execute({"action": "play", "target": "spotify:track:abc"})

        mock_player.add_to_queue.assert_called_once_with("spotify:track:abc")
        mock_player.skip_next.assert_called_once()

    @patch("clautify.dsl.executor.Player")
    def test_play_uri_with_context(self, MockPlayer, executor):
        mock_player = MagicMock()
        MockPlayer.return_value = mock_player

        result = executor.execute({
            "action": "play",
            "target": "spotify:track:abc",
            "context": "spotify:playlist:def",
        })

        mock_player.play_track.assert_called_once_with("spotify:track:abc", "spotify:playlist:def")


# ── Query Dispatch ────────────────────────────────────────────────


class TestQueries:
    @patch("clautify.dsl.executor.Song")
    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_search_tracks(self, MockPP, MockSong, executor):
        mock_song = MagicMock()
        mock_song.query_songs.return_value = {"data": "results"}
        MockSong.return_value = mock_song

        result = executor.execute({"query": "search", "term": "jazz", "limit": 5})

        mock_song.query_songs.assert_called_once_with("jazz", limit=5, offset=0)
        assert result["data"] == {"data": "results"}

    @patch("clautify.dsl.executor.Artist")
    def test_search_artists(self, MockArtist, executor):
        mock_artist = MagicMock()
        mock_artist.query_artists.return_value = {"data": "artist_results"}
        MockArtist.return_value = mock_artist

        result = executor.execute({"query": "search", "term": "jazz", "type": "artists"})

        mock_artist.query_artists.assert_called_once_with("jazz", limit=10, offset=0)

    @patch("clautify.dsl.executor.Player")
    def test_now_playing(self, MockPlayer, executor):
        mock_player = MagicMock()
        mock_player.state = {"track": "test"}
        MockPlayer.return_value = mock_player

        result = executor.execute({"query": "now_playing"})

        assert result["query"] == "now_playing"
        assert result["data"] == {"track": "test"}

    @patch("clautify.dsl.executor.Player")
    def test_get_queue(self, MockPlayer, executor):
        mock_player = MagicMock()
        mock_player.next_songs_in_queue = ["song1", "song2"]
        MockPlayer.return_value = mock_player

        result = executor.execute({"query": "get_queue"})

        assert result["data"] == ["song1", "song2"]

    @patch("clautify.dsl.executor.Player")
    def test_get_devices(self, MockPlayer, executor):
        mock_player = MagicMock()
        mock_player.device_ids = {"device1": "info"}
        MockPlayer.return_value = mock_player

        result = executor.execute({"query": "get_devices"})

        assert result["data"] == {"device1": "info"}

    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_library(self, MockPP, executor):
        mock_pp = MagicMock()
        mock_pp.get_library.return_value = {"items": []}
        MockPP.return_value = mock_pp

        result = executor.execute({"query": "library"})

        mock_pp.get_library.assert_called_once_with(50)

    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_recommend(self, MockPP, executor):
        mock_pp = MagicMock()
        mock_pp.recommended_songs.return_value = {"tracks": []}
        MockPP.return_value = mock_pp

        result = executor.execute({
            "query": "recommend",
            "target": "spotify:playlist:abc",
            "n": 5,
        })

        mock_pp.recommended_songs.assert_called_once_with(num_songs=5)

    @patch("clautify.dsl.executor.Player")
    def test_history_with_limit(self, MockPlayer, executor):
        mock_player = MagicMock()
        mock_player.last_songs_played = ["a", "b", "c", "d", "e"]
        MockPlayer.return_value = mock_player

        result = executor.execute({"query": "history", "limit": 3})

        assert result["data"] == ["a", "b", "c"]

    @patch("clautify.dsl.executor.Player")
    def test_history_no_limit(self, MockPlayer, executor):
        mock_player = MagicMock()
        mock_player.last_songs_played = ["a", "b", "c"]
        MockPlayer.return_value = mock_player

        result = executor.execute({"query": "history"})

        assert result["data"] == ["a", "b", "c"]


class TestInfoQuery:
    @patch("clautify.dsl.executor.Song")
    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_info_track(self, MockPP, MockSong, executor):
        mock_song = MagicMock()
        mock_song.get_track_info.return_value = {"name": "Bohemian Rhapsody"}
        MockSong.return_value = mock_song

        result = executor.execute({"query": "info", "target": "spotify:track:abc123"})

        mock_song.get_track_info.assert_called_once_with("abc123")
        assert result["data"] == {"name": "Bohemian Rhapsody"}

    @patch("clautify.dsl.executor.Artist")
    def test_info_artist(self, MockArtist, executor):
        mock_artist = MagicMock()
        mock_artist.get_artist.return_value = {"name": "Queen"}
        MockArtist.return_value = mock_artist

        result = executor.execute({"query": "info", "target": "spotify:artist:xyz"})

        mock_artist.get_artist.assert_called_once_with("xyz")
        assert result["data"] == {"name": "Queen"}

    @patch("clautify.dsl.executor.PublicAlbum")
    def test_info_album(self, MockAlbum, executor):
        mock_album = MagicMock()
        mock_album.get_album_info.return_value = {"name": "A Night at the Opera"}
        MockAlbum.return_value = mock_album

        result = executor.execute({"query": "info", "target": "spotify:album:abc"})

        MockAlbum.assert_called_once_with("abc")
        mock_album.get_album_info.assert_called_once()

    @patch("clautify.playlist.PublicPlaylist")
    def test_info_playlist(self, MockPubPL, executor):
        mock_pl = MagicMock()
        mock_pl.get_playlist_info.return_value = {"name": "Road Trip"}
        MockPubPL.return_value = mock_pl

        result = executor.execute({"query": "info", "target": "spotify:playlist:abc"})

        MockPubPL.assert_called_once_with("abc")
        mock_pl.get_playlist_info.assert_called_once()

    def test_info_requires_uri(self, executor):
        with pytest.raises(DSLError, match="Use search to find URIs first"):
            executor.execute({"query": "info", "target": "some string"})

    def test_info_unknown_kind(self, executor):
        with pytest.raises(DSLError, match="Cannot get info"):
            executor.execute({"query": "info", "target": "spotify:show:abc"})


# ── Queue with String ────────────────────────────────────────────


class TestQueueString:
    @patch("clautify.dsl.executor.Player")
    @patch("clautify.dsl.executor.Song")
    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_queue_string_resolves(self, MockPP, MockSong, MockPlayer, executor):
        mock_song = MagicMock()
        mock_song.query_songs.return_value = {
            "data": {
                "searchV2": {
                    "tracksV2": {
                        "items": [
                            {"item": {"data": {"uri": "spotify:track:resolved"}}}
                        ]
                    }
                }
            }
        }
        MockSong.return_value = mock_song

        mock_player = MagicMock()
        MockPlayer.return_value = mock_player

        result = executor.execute({"action": "queue", "target": "stairway to heaven"})

        mock_song.query_songs.assert_called_once_with("stairway to heaven", limit=1)
        mock_player.add_to_queue.assert_called_once_with("spotify:track:resolved")


# ── End-to-End (Parser → Executor) ──────────────────────────────


class TestEndToEnd:
    """Integration tests: command string → parser → executor → result."""

    @patch("clautify.dsl.executor.Player")
    def test_pause_e2e(self, MockPlayer, executor):
        from clautify.dsl.parser import parse
        mock_player = MagicMock()
        MockPlayer.return_value = mock_player

        cmd = parse("pause")
        result = executor.execute(cmd)

        mock_player.pause.assert_called_once()
        assert result["status"] == "ok"

    @patch("clautify.dsl.executor.Artist")
    def test_search_e2e(self, MockArtist, executor):
        from clautify.dsl.parser import parse
        mock_artist = MagicMock()
        mock_artist.query_artists.return_value = {"data": "results"}
        MockArtist.return_value = mock_artist

        cmd = parse('search "jazz" artists limit 5')
        result = executor.execute(cmd)

        mock_artist.query_artists.assert_called_once_with("jazz", limit=5, offset=0)
        assert result["query"] == "search"
        assert result["type"] == "artists"

    @patch("clautify.dsl.executor.Player")
    def test_volume_mode_e2e(self, MockPlayer, executor):
        from clautify.dsl.parser import parse
        mock_player = MagicMock()
        MockPlayer.return_value = mock_player

        cmd = parse("volume 70 mode shuffle")
        result = executor.execute(cmd)

        mock_player.set_volume.assert_called_once_with(0.7)
        mock_player.set_shuffle.assert_called_once_with(True)
        assert result["action"] == "set"


# ── Error Wrapping ────────────────────────────────────────────────


class TestErrorWrapping:
    def test_unknown_action(self, executor):
        with pytest.raises(DSLError, match="Unknown action"):
            executor.execute({"action": "explode"})

    def test_unknown_query(self, executor):
        with pytest.raises(DSLError, match="Unknown query"):
            executor.execute({"query": "explode"})

    def test_no_action_or_query(self, executor):
        with pytest.raises(DSLError, match="no action or query"):
            executor.execute({"foo": "bar"})

    @patch("clautify.dsl.executor.Player")
    def test_clautify_exception_wrapped(self, MockPlayer, executor):
        mock_player = MagicMock()
        mock_player.pause.side_effect = RuntimeError("connection lost")
        MockPlayer.return_value = mock_player

        with pytest.raises(DSLError, match="connection lost"):
            executor.execute({"action": "pause"})


# ── Device Resolution (Fix 1) ───────────────────────────────────


def _make_mock_devices(*name_id_pairs):
    """Helper: build a mock Devices with named Device objects."""
    devices = {}
    for i, (name, device_id) in enumerate(name_id_pairs):
        d = MagicMock()
        d.name = name
        d.device_id = device_id
        devices[str(i)] = d
    mock = MagicMock()
    mock.devices = devices
    return mock


class TestDeviceResolution:
    @patch("clautify.dsl.executor.Player")
    def test_resolve_by_name(self, MockPlayer, executor):
        mock_player = MagicMock()
        mock_player.device_id = "origin"
        mock_player.device_ids = _make_mock_devices(
            ("Living Room", "lr_hex"), ("Bedroom", "br_hex"),
        )
        MockPlayer.return_value = mock_player

        executor.execute({"action": "set", "device": "Bedroom"})

        mock_player.transfer_player.assert_called_once_with("origin", "br_hex")

    @patch("clautify.dsl.executor.Player")
    def test_case_insensitive(self, MockPlayer, executor):
        mock_player = MagicMock()
        mock_player.device_id = "origin"
        mock_player.device_ids = _make_mock_devices(("Kitchen Speaker", "ks_hex"))
        MockPlayer.return_value = mock_player

        executor.execute({"action": "set", "device": "kitchen speaker"})

        mock_player.transfer_player.assert_called_once_with("origin", "ks_hex")

    @patch("clautify.dsl.executor.Player")
    def test_unknown_device_error(self, MockPlayer, executor):
        mock_player = MagicMock()
        mock_player.device_ids = _make_mock_devices(("Kitchen", "k_hex"))
        MockPlayer.return_value = mock_player

        with pytest.raises(DSLError, match="Device 'Garage' not found"):
            executor.execute({"action": "set", "device": "Garage"})


# ── Volume Validation (Fix 2) ───────────────────────────────────


class TestVolumeValidation:
    @patch("clautify.dsl.executor.Player")
    def test_volume_in_range(self, MockPlayer, executor):
        mock_player = MagicMock()
        MockPlayer.return_value = mock_player

        executor.execute({"action": "pause", "volume": 70})

        mock_player.set_volume.assert_called_once_with(0.7)

    @patch("clautify.dsl.executor.Player")
    def test_volume_zero(self, MockPlayer, executor):
        mock_player = MagicMock()
        MockPlayer.return_value = mock_player

        executor.execute({"action": "pause", "volume": 0})

        mock_player.set_volume.assert_called_once_with(0)

    @patch("clautify.dsl.executor.Player")
    def test_volume_100(self, MockPlayer, executor):
        mock_player = MagicMock()
        MockPlayer.return_value = mock_player

        executor.execute({"action": "pause", "volume": 100})

        mock_player.set_volume.assert_called_once_with(1.0)

    @patch("clautify.dsl.executor.Player")
    def test_volume_over_100_raises(self, MockPlayer, executor):
        MockPlayer.return_value = MagicMock()

        with pytest.raises(DSLError, match="Volume must be 0-100"):
            executor.execute({"action": "pause", "volume": 150})

    @patch("clautify.dsl.executor.Player")
    def test_volume_negative_raises(self, MockPlayer, executor):
        MockPlayer.return_value = MagicMock()

        with pytest.raises(DSLError, match="Volume must be 0-100"):
            executor.execute({"action": "pause", "volume": -5})


# ── Play String with Context (Fix 3) ────────────────────────────


class TestPlayStringWithContext:
    @patch("clautify.dsl.executor.Player")
    @patch("clautify.dsl.executor.Song")
    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_string_target_with_uri_context(self, MockPP, MockSong, MockPlayer, executor):
        mock_song = MagicMock()
        mock_song.query_songs.return_value = {
            "data": {"searchV2": {"tracksV2": {"items": [
                {"item": {"data": {"uri": "spotify:track:found"}}}
            ]}}}
        }
        MockSong.return_value = mock_song
        mock_player = MagicMock()
        MockPlayer.return_value = mock_player

        result = executor.execute({
            "action": "play",
            "target": "jazz",
            "context": "spotify:playlist:abc",
        })

        mock_song.query_songs.assert_called_once_with("jazz", limit=1)
        mock_player.play_track.assert_called_once_with(
            "spotify:track:found", "spotify:playlist:abc"
        )
        assert result["resolved_uri"] == "spotify:track:found"
        assert result["context"] == "spotify:playlist:abc"

    @patch("clautify.dsl.executor.Player")
    @patch("clautify.dsl.executor.Song")
    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_string_target_with_string_context_raises(self, MockPP, MockSong, MockPlayer, executor):
        mock_song = MagicMock()
        mock_song.query_songs.return_value = {
            "data": {"searchV2": {"tracksV2": {"items": [
                {"item": {"data": {"uri": "spotify:track:found"}}}
            ]}}}
        }
        MockSong.return_value = mock_song
        MockPlayer.return_value = MagicMock()

        with pytest.raises(DSLError, match="requires a playlist URI"):
            executor.execute({
                "action": "play",
                "target": "jazz",
                "context": "Classic Rock",
            })


# ── Recommend Validation (Fix 7) ────────────────────────────────


class TestRecommendValidation:
    def test_recommend_non_uri_raises(self, executor):
        with pytest.raises(DSLError, match="recommend requires a playlist URI"):
            executor.execute({"query": "recommend", "target": "Road Trip", "n": 5})

    def test_recommend_non_playlist_uri_raises(self, executor):
        with pytest.raises(DSLError, match="recommend requires a playlist URI"):
            executor.execute({
                "query": "recommend",
                "target": "spotify:track:abc",
                "n": 5,
            })

    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_recommend_playlist_uri_ok(self, MockPP, executor):
        mock_pp = MagicMock()
        mock_pp.recommended_songs.return_value = {"tracks": []}
        MockPP.return_value = mock_pp

        result = executor.execute({
            "query": "recommend",
            "target": "spotify:playlist:abc",
            "n": 5,
        })

        assert result["status"] == "ok"


# ── Parse Errors (Fix 8) ────────────────────────────────────────


class TestParseErrors:
    def test_invalid_command_string(self):
        from clautify.dsl import SpotifySession

        login = MagicMock()
        with patch("clautify.dsl.executor.Player"):
            session = SpotifySession(login, eager=False)

        with pytest.raises(DSLError, match="Invalid command"):
            session.run("explode everything")

    def test_parse_error_lists_valid_commands(self):
        from clautify.dsl import SpotifySession

        login = MagicMock()
        with patch("clautify.dsl.executor.Player"):
            session = SpotifySession(login, eager=False)

        with pytest.raises(DSLError, match="Valid commands:"):
            session.run("gibberish xyz 123")

    def test_empty_command(self):
        from clautify.dsl import SpotifySession

        login = MagicMock()
        with patch("clautify.dsl.executor.Player"):
            session = SpotifySession(login, eager=False)

        with pytest.raises(DSLError):
            session.run("")


# ── Session Auth (Cookie Persistence) ───────────────────────────


class TestSessionAuth:
    def test_setup_creates_file(self, tmp_path):
        from clautify.dsl import SpotifySession

        dest = tmp_path / "session.json"
        result_path = SpotifySession.setup("FAKE_SP_DC_VALUE", path=dest)

        assert result_path == dest
        assert dest.exists()

        import json
        data = json.loads(dest.read_text())
        assert data["cookies"]["sp_dc"] == "FAKE_SP_DC_VALUE"
        assert data["identifier"] == "default"

    def test_setup_empty_sp_dc_raises(self):
        from clautify.dsl import SpotifySession

        with pytest.raises(DSLError, match="sp_dc cookie value is required"):
            SpotifySession.setup("")

    @patch("clautify.dsl.Login.from_cookies")
    def test_from_config_loads_session(self, mock_from_cookies, tmp_path):
        from clautify.dsl import SpotifySession

        mock_login = MagicMock()
        mock_from_cookies.return_value = mock_login

        # Setup first
        dest = tmp_path / "session.json"
        SpotifySession.setup("FAKE_SP_DC", path=dest)

        # Load from config
        with patch("clautify.dsl.executor.Player"):
            session = SpotifySession.from_config(path=dest, eager=False)

        # Verify from_cookies was called with correct dump
        call_args = mock_from_cookies.call_args
        dump = call_args[0][0]
        assert dump["cookies"]["sp_dc"] == "FAKE_SP_DC"
        assert dump["password"] == ""

    def test_from_config_missing_file(self, tmp_path):
        from clautify.dsl import SpotifySession

        with pytest.raises(DSLError, match="No session file found"):
            SpotifySession.from_config(path=tmp_path / "nonexistent.json")
