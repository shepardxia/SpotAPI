"""Tests for SpotifySession — the public API.

Tests run(command) end-to-end: parse → execute → result dict.
SpotAPI classes are mocked at the module boundary (they make real HTTP calls).
Assertions check the returned result dict, not internal mock calls.
"""

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from clautify.dsl import SpotifySession
from clautify.dsl.executor import DSLError
from clautify.exceptions import WebSocketError

# ── Fixtures ────────────────────────────────────────────────────────


def _mock_player(**overrides):
    p = MagicMock()
    p.state = MagicMock()
    p.active_id = "dev0"
    p.device_id = "dev0"
    dev = MagicMock()
    dev.volume = 32768  # ~50%
    dev.name = "Den"
    dev.device_id = "dev0"
    devices = MagicMock()
    devices.devices = {"dev0": dev}
    p.device_ids = devices
    p.next_songs_in_queue = []
    p.last_songs_played = []
    for k, v in overrides.items():
        setattr(p, k, v)
    return p


@pytest.fixture
def session():
    login = MagicMock()
    with (
        patch("clautify.dsl.executor.Player") as P,
        patch("clautify.dsl.executor.Song") as S,
        patch("clautify.dsl.executor.Artist") as A,
        patch("clautify.dsl.executor.PrivatePlaylist") as PP,
    ):
        P.return_value = _mock_player()
        S.return_value = MagicMock()
        A.return_value = MagicMock()
        PP.return_value = MagicMock()
        s = SpotifySession(login, eager=False)
        s._mocks = {"Player": P, "Song": S, "Artist": A, "PP": PP}
        yield s


# ── Actions ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "cmd, expected_action",
    [
        ("pause", "pause"),
        ("resume", "resume"),
    ],
)
def test_simple_actions(session, cmd, expected_action):
    r = session.run(cmd)
    assert r["status"] == "ok"
    assert r["action"] == expected_action


def test_skip(session):
    r = session.run("skip 3")
    assert r["status"] == "ok"
    assert r["action"] == "skip"


def test_play_uri(session):
    r = session.run("play spotify:track:abc")
    assert r["status"] == "ok"
    assert r["action"] == "play"
    assert r["kind"] == "track"


def test_play_cached_string(session):
    session._executor._cache.add("track", "jazz", "spotify:track:found")
    r = session.run('play "jazz"')
    assert r["status"] == "ok"
    assert r["resolved_uri"] == "spotify:track:found"


def test_play_uncached_string_raises(session):
    with pytest.raises(DSLError, match="not found.*search first"):
        session.run('play "nonexistent xyz"')


def test_play_with_context(session):
    r = session.run("play spotify:track:abc in spotify:playlist:def")
    assert r["status"] == "ok"
    assert r["context"] == "spotify:playlist:def"


def test_queue(session):
    r = session.run("queue spotify:track:abc")
    assert r["status"] == "ok"
    assert r["action"] == "queue"


# ── Table-driven actions ────────────────────────────────────────────


def test_target_action(session):
    r = session.run("like spotify:track:abc")
    assert r["status"] == "ok"


# ── State modifiers ─────────────────────────────────────────────────


def test_volume(session):
    r = session.run("volume 70")
    assert r["status"] == "ok"
    assert r["volume"] == 70.0


def test_volume_out_of_range(session):
    with pytest.raises(DSLError, match="Volume must be 0-100"):
        session.run("volume 150")


def test_mode(session):
    r = session.run("mode shuffle")
    assert r["status"] == "ok"
    assert r["mode"] == "shuffle"


def test_device_transfer(session):
    r = session.run('on "Den"')
    assert r["status"] == "ok"
    assert r["device"] == "Den"


def test_device_not_found(session):
    with pytest.raises(DSLError, match="not found"):
        session.run('on "Garage"')


# ── Queries ─────────────────────────────────────────────────────────


def test_now_playing(session):
    r = session.run("now playing")
    assert r["status"] == "ok"
    assert r["query"] == "now_playing"
    assert "data" in r


def test_search(session):
    mock_song = session._mocks["Song"].return_value
    mock_song.query_songs.return_value = {"data": {"searchV2": {"tracksV2": {"items": []}}}}
    r = session.run('search "jazz" tracks')
    assert r["status"] == "ok"
    assert r["query"] == "search"
    assert r["type"] == "tracks"


# ── Error handling ──────────────────────────────────────────────────


def test_invalid_command(session):
    with pytest.raises(DSLError, match="Invalid command"):
        session.run("explode everything")


def test_unknown_action(session):
    with pytest.raises(DSLError, match="Unknown action"):
        session._executor.execute({"action": "explode"})


def test_exception_wraps_as_dsl_error(session):
    player = session._mocks["Player"].return_value
    player.pause.side_effect = RuntimeError("connection lost")
    with pytest.raises(DSLError, match="connection lost"):
        session.run("pause")


# ── WebSocket reconnect ────────────────────────────────────────────


def test_ws_error_retries_and_succeeds(session):
    player = session._mocks["Player"].return_value
    call_count = 0

    def pause_side_effect():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise WebSocketError("disconnected")

    player.pause.side_effect = pause_side_effect
    r = session.run("pause")
    assert r["status"] == "ok"
    assert call_count == 2  # first failed, second succeeded


def test_ws_error_both_attempts_raises(session):
    player = session._mocks["Player"].return_value
    player.pause.side_effect = WebSocketError("dead")
    with pytest.raises(DSLError):
        session.run("pause")


def test_non_ws_error_no_retry(session):
    player = session._mocks["Player"].return_value
    player.pause.side_effect = DSLError("bad state")
    with pytest.raises(DSLError, match="bad state"):
        session.run("pause")


# ── Session setup ───────────────────────────────────────────────────


def test_setup_creates_file(tmp_path):
    import json

    dest = tmp_path / "session.json"
    SpotifySession.setup("FAKE_SP_DC", path=dest)
    assert dest.exists()
    assert json.loads(dest.read_text())["cookies"]["sp_dc"] == "FAKE_SP_DC"


def test_setup_empty_raises():
    with pytest.raises(DSLError, match="sp_dc cookie value is required"):
        SpotifySession.setup("")


def test_from_config_missing_file(tmp_path):
    with pytest.raises(DSLError, match="No session file found"):
        SpotifySession.from_config(path=tmp_path / "nope.json")
