"""Tests for the DSL executor — mocked SpotAPI classes, no network calls."""

from unittest.mock import MagicMock, patch

import pytest

from clautify.dsl.executor import DSLError, SpotifyExecutor


@pytest.fixture
def login():
    return MagicMock()


@pytest.fixture
def executor(login):
    return SpotifyExecutor(login, eager=False)


# ── Helpers ──────────────────────────────────────────────────────


_SEARCH_HIT = {"data": {"searchV2": {"tracksV2": {"items": [{"item": {"data": {"uri": "spotify:track:found123"}}}]}}}}

_SEARCH_EMPTY = {"data": {"searchV2": {"tracksV2": {"items": []}}}}


def _make_mock_devices(*name_id_pairs):
    devices = {}
    for i, (name, device_id) in enumerate(name_id_pairs):
        d = MagicMock()
        d.name = name
        d.device_id = device_id
        devices[str(i)] = d
    mock = MagicMock()
    mock.devices = devices
    return mock


def _make_player_with_volume(MockPlayer, volume_16bit, active_id="active_dev"):
    mock_device = MagicMock()
    mock_device.volume = volume_16bit
    mock_devices = MagicMock()
    mock_devices.devices = {active_id: mock_device}
    mock_player = MagicMock()
    mock_player.active_id = active_id
    mock_player.device_ids = mock_devices
    MockPlayer.return_value = mock_player
    return mock_player


# ── Lazy Initialization ──────────────────────────────────────────


class TestLazyInit:
    @patch("clautify.dsl.executor.Player")
    def test_player_created_on_first_use(self, MockPlayer, executor):
        MockPlayer.return_value = MagicMock()
        executor.execute({"action": "pause"})
        MockPlayer.assert_called_once_with(executor._login)

    @patch("clautify.dsl.executor.Song")
    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_search_does_not_create_player(self, MockPP, MockSong, executor):
        mock_song = MagicMock()
        mock_song.query_songs.return_value = _SEARCH_HIT
        MockSong.return_value = mock_song
        executor.execute({"query": "search", "term": "jazz"})
        assert executor._player is None


# ── Table-driven actions ─────────────────────────────────────────


class TestTableDrivenActions:
    @pytest.mark.parametrize(
        "action, target, service_attr, method, mock_path",
        [
            ("like", "spotify:track:abc", "song", "like_song", "clautify.dsl.executor.Song"),
            ("unlike", "spotify:track:abc", "song", "unlike_song", "clautify.dsl.executor.Song"),
            ("follow", "spotify:artist:abc", "artist", "follow", "clautify.dsl.executor.Artist"),
            ("unfollow", "spotify:artist:abc", "artist", "unfollow", "clautify.dsl.executor.Artist"),
        ],
    )
    def test_simple_target_actions(self, action, target, service_attr, method, mock_path, executor):
        with patch(mock_path) as MockCls:
            mock_svc = MagicMock()
            MockCls.return_value = mock_svc
            with patch("clautify.dsl.executor.PrivatePlaylist"):
                result = executor.execute({"action": action, "target": target})
            getattr(mock_svc, method).assert_called_once()
            assert result["status"] == "ok"

    @pytest.mark.parametrize(
        "action, method",
        [
            ("save", "add_to_library"),
            ("unsave", "remove_from_library"),
            ("playlist_delete", "delete_playlist"),
        ],
    )
    def test_playlist_table_actions(self, action, method, executor):
        with patch("clautify.dsl.executor.PrivatePlaylist") as MockPP:
            mock_pp = MagicMock()
            MockPP.return_value = mock_pp
            result = executor.execute({"action": action, "target": "spotify:playlist:abc"})
            getattr(mock_pp, method).assert_called_once()
            assert result["status"] == "ok"

    @pytest.mark.parametrize("action", ["pause", "resume"])
    def test_pause_resume(self, action, executor):
        with patch("clautify.dsl.executor.Player") as MockPlayer:
            MockPlayer.return_value = MagicMock()
            result = executor.execute({"action": action})
            getattr(MockPlayer.return_value, action).assert_called_once()
            assert result["action"] == action


# ── Complex actions ──────────────────────────────────────────────


class TestActions:
    @patch("clautify.dsl.executor.Player")
    def test_skip_forward(self, MockPlayer, executor):
        MockPlayer.return_value = MagicMock()
        executor.execute({"action": "skip", "n": 3})
        assert MockPlayer.return_value.skip_next.call_count == 3

    @patch("clautify.dsl.executor.Player")
    def test_skip_backward(self, MockPlayer, executor):
        MockPlayer.return_value = MagicMock()
        executor.execute({"action": "skip", "n": -2})
        assert MockPlayer.return_value.skip_prev.call_count == 2

    @patch("clautify.dsl.executor.Player")
    def test_seek(self, MockPlayer, executor):
        MockPlayer.return_value = MagicMock()
        executor.execute({"action": "seek", "position_ms": 30000})
        MockPlayer.return_value.seek_to.assert_called_once_with(30000)

    @patch("clautify.dsl.executor.Player")
    def test_queue_uri(self, MockPlayer, executor):
        MockPlayer.return_value = MagicMock()
        executor.execute({"action": "queue", "target": "spotify:track:abc"})
        MockPlayer.return_value.add_to_queue.assert_called_once_with("spotify:track:abc")


# ── Playlist handlers ────────────────────────────────────────────


class TestPlaylistHandlers:
    @patch("clautify.dsl.executor.Song")
    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_playlist_add(self, MockPP, MockSong, executor):
        mock_song = MagicMock()
        MockSong.return_value = mock_song
        executor.execute(
            {
                "action": "playlist_add",
                "track": "spotify:track:abc",
                "playlist": "spotify:playlist:def",
            }
        )
        mock_song.add_song_to_playlist.assert_called_once_with("abc")

    @patch("clautify.dsl.executor.Song")
    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_playlist_remove(self, MockPP, MockSong, executor):
        mock_song = MagicMock()
        MockSong.return_value = mock_song
        executor.execute(
            {
                "action": "playlist_remove",
                "track": "spotify:track:abc",
                "playlist": "spotify:playlist:def",
            }
        )
        mock_song.remove_song_from_playlist.assert_called_once_with(song_id="abc")

    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_create_playlist(self, MockPP, executor):
        mock_pp = MagicMock()
        mock_pp.create_playlist.return_value = "new_id"
        MockPP.return_value = mock_pp
        result = executor.execute({"action": "playlist_create", "name": "Road Trip"})
        mock_pp.create_playlist.assert_called_once_with("Road Trip")
        assert result["playlist_id"] == "new_id"


# ── State Modifiers ──────────────────────────────────────────────


class TestStateModifiers:
    @pytest.mark.parametrize(
        "mode, shuffle, repeat",
        [
            ("shuffle", True, False),
            ("repeat", False, True),
            ("normal", False, False),
        ],
    )
    def test_mode(self, mode, shuffle, repeat, executor):
        with patch("clautify.dsl.executor.Player") as MockPlayer:
            MockPlayer.return_value = MagicMock()
            executor.execute({"action": "set", "mode": mode})
            MockPlayer.return_value.set_shuffle.assert_called_once_with(shuffle)
            MockPlayer.return_value.repeat_track.assert_called_once_with(repeat)

    @patch("clautify.dsl.executor.Player")
    def test_device_transfer(self, MockPlayer, executor):
        mock_player = MagicMock()
        mock_player.device_id = "origin"
        mock_player.device_ids = _make_mock_devices(("Living Room", "lr_hex"))
        MockPlayer.return_value = mock_player
        executor.execute({"action": "set", "device": "Living Room"})
        mock_player.transfer_player.assert_called_once_with("origin", "lr_hex")

    @patch("clautify.dsl.executor.Player")
    def test_volume(self, MockPlayer, executor):
        MockPlayer.return_value = MagicMock()
        executor.execute({"action": "pause", "volume": 70})
        MockPlayer.return_value.set_volume.assert_called_once_with(0.7)

    @pytest.mark.parametrize("vol", [150, -5])
    def test_volume_out_of_range(self, vol, executor):
        with patch("clautify.dsl.executor.Player") as MockPlayer:
            MockPlayer.return_value = MagicMock()
            with pytest.raises(DSLError, match="Volume must be 0-100"):
                executor.execute({"action": "pause", "volume": vol})


# ── Relative Volume ──────────────────────────────────────────────


class TestRelativeVolume:
    @patch("clautify.dsl.executor.Player")
    def test_increase(self, MockPlayer, executor):
        mock_player = _make_player_with_volume(MockPlayer, 32768)  # ~50%
        executor.execute({"action": "set", "volume_rel": 10})
        call_arg = mock_player.set_volume.call_args[0][0]
        assert abs(call_arg - 0.6) < 0.01

    @pytest.mark.parametrize(
        "volume_16bit, delta, expected",
        [
            (62000, 20, 1.0),  # clamp at 100
            (3277, -20, 0.0),  # clamp at 0
        ],
    )
    def test_clamp(self, volume_16bit, delta, expected, executor):
        with patch("clautify.dsl.executor.Player") as MockPlayer:
            mock_player = _make_player_with_volume(MockPlayer, volume_16bit)
            executor.execute({"action": "set", "volume_rel": delta})
            mock_player.set_volume.assert_called_once_with(expected)

    @patch("clautify.dsl.executor.Player")
    def test_composed_with_action(self, MockPlayer, executor):
        mock_player = _make_player_with_volume(MockPlayer, 32768)
        executor.execute({"action": "pause", "volume_rel": 10})
        mock_player.pause.assert_called_once()
        assert mock_player.set_volume.called


# ── String Resolution (play/queue) ──────────────────────────────


class TestStringResolution:
    @patch("clautify.dsl.executor.Player")
    @patch("clautify.dsl.executor.Song")
    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_play_string_resolves(self, MockPP, MockSong, MockPlayer, executor):
        MockSong.return_value = MagicMock(query_songs=MagicMock(return_value=_SEARCH_HIT))
        mock_player = MagicMock()
        MockPlayer.return_value = mock_player
        result = executor.execute({"action": "play", "target": "jazz"})
        mock_player.add_to_queue.assert_called_once_with("spotify:track:found123")
        mock_player.skip_next.assert_called_once()
        assert result["resolved_uri"] == "spotify:track:found123"

    @patch("clautify.dsl.executor.Player")
    @patch("clautify.dsl.executor.Song")
    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_play_string_no_results(self, MockPP, MockSong, MockPlayer, executor):
        MockSong.return_value = MagicMock(query_songs=MagicMock(return_value=_SEARCH_EMPTY))
        MockPlayer.return_value = MagicMock()
        with pytest.raises(DSLError, match="No results"):
            executor.execute({"action": "play", "target": "nonexistent xyz"})

    @patch("clautify.dsl.executor.Player")
    def test_play_uri_no_context(self, MockPlayer, executor):
        mock_player = MagicMock()
        MockPlayer.return_value = mock_player
        executor.execute({"action": "play", "target": "spotify:track:abc"})
        mock_player.add_to_queue.assert_called_once_with("spotify:track:abc")
        mock_player.skip_next.assert_called_once()

    @patch("clautify.dsl.executor.Player")
    def test_play_uri_with_context(self, MockPlayer, executor):
        mock_player = MagicMock()
        MockPlayer.return_value = mock_player
        executor.execute(
            {
                "action": "play",
                "target": "spotify:track:abc",
                "context": "spotify:playlist:def",
            }
        )
        mock_player.play_track.assert_called_once_with("spotify:track:abc", "spotify:playlist:def")

    @patch("clautify.dsl.executor.Player")
    @patch("clautify.dsl.executor.Song")
    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_play_string_with_uri_context(self, MockPP, MockSong, MockPlayer, executor):
        MockSong.return_value = MagicMock(query_songs=MagicMock(return_value=_SEARCH_HIT))
        mock_player = MagicMock()
        MockPlayer.return_value = mock_player
        executor.execute(
            {
                "action": "play",
                "target": "jazz",
                "context": "spotify:playlist:abc",
            }
        )
        mock_player.play_track.assert_called_once_with("spotify:track:found123", "spotify:playlist:abc")

    @patch("clautify.dsl.executor.Player")
    @patch("clautify.dsl.executor.Song")
    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_play_string_with_string_context_raises(self, MockPP, MockSong, MockPlayer, executor):
        MockSong.return_value = MagicMock(query_songs=MagicMock(return_value=_SEARCH_HIT))
        MockPlayer.return_value = MagicMock()
        with pytest.raises(DSLError, match="requires a playlist URI"):
            executor.execute({"action": "play", "target": "jazz", "context": "Classic Rock"})

    @patch("clautify.dsl.executor.Player")
    @patch("clautify.dsl.executor.Song")
    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_queue_string_resolves(self, MockPP, MockSong, MockPlayer, executor):
        MockSong.return_value = MagicMock(query_songs=MagicMock(return_value=_SEARCH_HIT))
        mock_player = MagicMock()
        MockPlayer.return_value = mock_player
        executor.execute({"action": "queue", "target": "stairway to heaven"})
        mock_player.add_to_queue.assert_called_once_with("spotify:track:found123")


# ── Query Dispatch ───────────────────────────────────────────────


class TestQueries:
    @pytest.mark.parametrize(
        "query, player_attr",
        [
            ("now_playing", "state"),
            ("get_queue", "next_songs_in_queue"),
            ("get_devices", "device_ids"),
        ],
    )
    def test_player_attr_queries(self, query, player_attr, executor):
        with patch("clautify.dsl.executor.Player") as MockPlayer:
            mock_player = MagicMock()
            setattr(mock_player, player_attr, {"test": "data"})
            MockPlayer.return_value = mock_player
            result = executor.execute({"query": query})
            assert result["data"] == {"test": "data"}

    @patch("clautify.dsl.executor.Song")
    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_search_tracks(self, MockPP, MockSong, executor):
        mock_song = MagicMock()
        mock_song.query_songs.return_value = {"data": "results"}
        MockSong.return_value = mock_song
        executor.execute({"query": "search", "term": "jazz", "limit": 5})
        mock_song.query_songs.assert_called_once_with("jazz", limit=5, offset=0)

    @patch("clautify.dsl.executor.Artist")
    def test_search_artists(self, MockArtist, executor):
        mock_artist = MagicMock()
        mock_artist.query_artists.return_value = {"data": "results"}
        MockArtist.return_value = mock_artist
        executor.execute({"query": "search", "term": "jazz", "type": "artists"})
        mock_artist.query_artists.assert_called_once_with("jazz", limit=10, offset=0)

    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_library(self, MockPP, executor):
        mock_pp = MagicMock()
        mock_pp.get_library.return_value = {"items": []}
        MockPP.return_value = mock_pp
        executor.execute({"query": "library"})
        mock_pp.get_library.assert_called_once_with(50)

    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_recommend(self, MockPP, executor):
        mock_pp = MagicMock()
        mock_pp.recommended_songs.return_value = {"tracks": []}
        MockPP.return_value = mock_pp
        executor.execute(
            {
                "query": "recommend",
                "target": "spotify:playlist:abc",
                "n": 5,
            }
        )
        mock_pp.recommended_songs.assert_called_once_with(num_songs=5)

    @patch("clautify.dsl.executor.Player")
    def test_history(self, MockPlayer, executor):
        mock_player = MagicMock()
        mock_player.last_songs_played = ["a", "b", "c", "d", "e"]
        MockPlayer.return_value = mock_player
        result = executor.execute({"query": "history", "limit": 3})
        assert result["data"] == ["a", "b", "c"]


# ── Info query ───────────────────────────────────────────────────


class TestInfoQuery:
    @pytest.mark.parametrize(
        "uri, mock_path, method, call_arg",
        [
            ("spotify:track:abc", "clautify.dsl.executor.Song", "get_track_info", "abc"),
            ("spotify:artist:abc", "clautify.dsl.executor.Artist", "get_artist", "abc"),
        ],
    )
    def test_info_by_kind(self, uri, mock_path, method, call_arg, executor):
        with patch(mock_path) as MockCls:
            mock_svc = MagicMock()
            getattr(mock_svc, method).return_value = {"name": "Test"}
            MockCls.return_value = mock_svc
            with patch("clautify.dsl.executor.PrivatePlaylist"):
                result = executor.execute({"query": "info", "target": uri})
            getattr(mock_svc, method).assert_called_once_with(call_arg)
            assert result["data"] == {"name": "Test"}

    @patch("clautify.dsl.executor.PublicAlbum")
    def test_info_album(self, MockAlbum, executor):
        mock_album = MagicMock()
        mock_album.get_album_info.return_value = {"name": "Test Album"}
        MockAlbum.return_value = mock_album
        executor.execute({"query": "info", "target": "spotify:album:abc"})
        MockAlbum.assert_called_once_with("abc")
        mock_album.get_album_info.assert_called_once()

    @patch("clautify.playlist.PublicPlaylist")
    def test_info_playlist(self, MockPubPL, executor):
        mock_pl = MagicMock()
        mock_pl.get_playlist_info.return_value = {"name": "Road Trip"}
        MockPubPL.return_value = mock_pl
        executor.execute({"query": "info", "target": "spotify:playlist:abc"})
        MockPubPL.assert_called_once_with("abc")

    def test_info_requires_uri(self, executor):
        with pytest.raises(DSLError, match="Use search to find URIs first"):
            executor.execute({"query": "info", "target": "some string"})

    def test_info_unknown_kind(self, executor):
        with pytest.raises(DSLError, match="Cannot get info"):
            executor.execute({"query": "info", "target": "spotify:show:abc"})


# ── Device Resolution ────────────────────────────────────────────


class TestDeviceResolution:
    @patch("clautify.dsl.executor.Player")
    def test_resolve_by_name(self, MockPlayer, executor):
        mock_player = MagicMock()
        mock_player.device_id = "origin"
        mock_player.device_ids = _make_mock_devices(
            ("Living Room", "lr_hex"),
            ("Bedroom", "br_hex"),
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


# ── Recommend Validation ─────────────────────────────────────────


class TestRecommendValidation:
    @pytest.mark.parametrize("target", ["Road Trip", "spotify:track:abc"])
    def test_invalid_target(self, target, executor):
        with pytest.raises(DSLError, match="recommend requires a playlist URI"):
            executor.execute({"query": "recommend", "target": target, "n": 5})

    @patch("clautify.dsl.executor.PrivatePlaylist")
    def test_valid_playlist_uri(self, MockPP, executor):
        mock_pp = MagicMock()
        mock_pp.recommended_songs.return_value = {"tracks": []}
        MockPP.return_value = mock_pp
        result = executor.execute(
            {
                "query": "recommend",
                "target": "spotify:playlist:abc",
                "n": 5,
            }
        )
        assert result["status"] == "ok"


# ── Error Handling ───────────────────────────────────────────────


class TestErrorHandling:
    def test_unknown_action(self, executor):
        with pytest.raises(DSLError, match="Unknown action"):
            executor.execute({"action": "explode"})

    def test_unknown_query(self, executor):
        with pytest.raises(DSLError, match="Unknown query"):
            executor.execute({"query": "explode"})

    @patch("clautify.dsl.executor.Player")
    def test_exception_wrapped(self, MockPlayer, executor):
        mock_player = MagicMock()
        mock_player.pause.side_effect = RuntimeError("connection lost")
        MockPlayer.return_value = mock_player
        with pytest.raises(DSLError, match="connection lost"):
            executor.execute({"action": "pause"})


# ── End-to-End ───────────────────────────────────────────────────


class TestEndToEnd:
    @patch("clautify.dsl.executor.Player")
    def test_full_pipeline(self, MockPlayer, executor):
        from clautify.dsl.parser import parse

        MockPlayer.return_value = MagicMock()
        cmd = parse("volume 70 mode shuffle")
        executor.execute(cmd)
        MockPlayer.return_value.set_volume.assert_called_once_with(0.7)
        MockPlayer.return_value.set_shuffle.assert_called_once_with(True)


# ── Session Auth ─────────────────────────────────────────────────


class TestSessionAuth:
    def test_setup_creates_file(self, tmp_path):
        import json

        from clautify.dsl import SpotifySession

        dest = tmp_path / "session.json"
        result_path = SpotifySession.setup("FAKE_SP_DC_VALUE", path=dest)
        assert result_path == dest
        assert dest.exists()
        data = json.loads(dest.read_text())
        assert data["cookies"]["sp_dc"] == "FAKE_SP_DC_VALUE"

    def test_setup_empty_sp_dc_raises(self):
        from clautify.dsl import SpotifySession

        with pytest.raises(DSLError, match="sp_dc cookie value is required"):
            SpotifySession.setup("")

    @patch("clautify.dsl.Login.from_cookies")
    def test_from_config_loads_session(self, mock_from_cookies, tmp_path):
        from clautify.dsl import SpotifySession

        mock_from_cookies.return_value = MagicMock()
        dest = tmp_path / "session.json"
        SpotifySession.setup("FAKE_SP_DC", path=dest)
        with patch("clautify.dsl.executor.Player"):
            SpotifySession.from_config(path=dest, eager=False)
        dump = mock_from_cookies.call_args[0][0]
        assert dump["cookies"]["sp_dc"] == "FAKE_SP_DC"

    def test_from_config_missing_file(self, tmp_path):
        from clautify.dsl import SpotifySession

        with pytest.raises(DSLError, match="No session file found"):
            SpotifySession.from_config(path=tmp_path / "nonexistent.json")


# ── Parse Error Wrapping ─────────────────────────────────────────


class TestParseErrors:
    def test_invalid_command_wraps_as_dsl_error(self):
        from clautify.dsl import SpotifySession

        login = MagicMock()
        with patch("clautify.dsl.executor.Player"):
            session = SpotifySession(login, eager=False)
        with pytest.raises(DSLError, match="Invalid command"):
            session.run("explode everything")
