"""Tests for the DSL parser — pure parsing, no network calls."""

import pytest

from clautify.dsl.parser import parse

# ── Simple keyword actions ───────────────────────────────────────


@pytest.mark.parametrize(
    "cmd, expected",
    [
        ("pause", {"action": "pause"}),
        ("resume", {"action": "resume"}),
        ("like spotify:track:abc", {"action": "like", "target": "spotify:track:abc"}),
        ("unlike spotify:track:abc", {"action": "unlike", "target": "spotify:track:abc"}),
        ("follow spotify:artist:abc", {"action": "follow", "target": "spotify:artist:abc"}),
        ("unfollow spotify:artist:abc", {"action": "unfollow", "target": "spotify:artist:abc"}),
        ("save spotify:playlist:abc", {"action": "save", "target": "spotify:playlist:abc"}),
        ("unsave spotify:playlist:abc", {"action": "unsave", "target": "spotify:playlist:abc"}),
    ],
)
def test_simple_keyword_actions(cmd, expected):
    assert parse(cmd) == expected


# ── Play action ──────────────────────────────────────────────────


class TestPlayAction:
    def test_play_quoted_string(self):
        assert parse('play "Bohemian Rhapsody"') == {
            "action": "play",
            "target": "Bohemian Rhapsody",
        }

    def test_play_uri(self):
        assert parse("play spotify:track:6rqhFgbbKwnb9MLmUQDhG6") == {
            "action": "play",
            "target": "spotify:track:6rqhFgbbKwnb9MLmUQDhG6",
        }

    def test_play_with_uri_context(self):
        assert parse("play spotify:track:abc in spotify:playlist:def") == {
            "action": "play",
            "target": "spotify:track:abc",
            "context": "spotify:playlist:def",
        }

    def test_play_with_string_context(self):
        assert parse('play "Dark Side" in "Classic Rock"') == {
            "action": "play",
            "target": "Dark Side",
            "context": "Classic Rock",
        }


# ── Skip / Seek / Queue ─────────────────────────────────────────


class TestSkip:
    def test_skip_default(self):
        assert parse("skip") == {"action": "skip", "n": 1}

    def test_skip_positive(self):
        assert parse("skip 3") == {"action": "skip", "n": 3}

    def test_skip_negative(self):
        assert parse("skip -1") == {"action": "skip", "n": -1}


def test_seek():
    assert parse("seek 30000") == {"action": "seek", "position_ms": 30000.0}


@pytest.mark.parametrize(
    "cmd, expected",
    [
        ("queue spotify:track:abc", {"action": "queue", "target": "spotify:track:abc"}),
        ('queue "Stairway to Heaven"', {"action": "queue", "target": "Stairway to Heaven"}),
    ],
)
def test_queue(cmd, expected):
    assert parse(cmd) == expected


# ── Playlist CRUD ────────────────────────────────────────────────


class TestPlaylistCRUD:
    def test_add_to_playlist(self):
        assert parse("add spotify:track:abc to spotify:playlist:def") == {
            "action": "playlist_add",
            "track": "spotify:track:abc",
            "playlist": "spotify:playlist:def",
        }

    def test_add_to_playlist_by_name(self):
        assert parse('add spotify:track:abc to "Road Trip"') == {
            "action": "playlist_add",
            "track": "spotify:track:abc",
            "playlist": "Road Trip",
        }

    def test_remove_from_playlist(self):
        assert parse("remove spotify:track:abc from spotify:playlist:def") == {
            "action": "playlist_remove",
            "track": "spotify:track:abc",
            "playlist": "spotify:playlist:def",
        }

    def test_create_playlist(self):
        assert parse('create playlist "Road Trip Mix"') == {
            "action": "playlist_create",
            "name": "Road Trip Mix",
        }

    def test_delete_playlist_uri(self):
        assert parse("delete playlist spotify:playlist:abc123") == {
            "action": "playlist_delete",
            "target": "spotify:playlist:abc123",
        }

    def test_delete_playlist_string(self):
        assert parse('delete playlist "Road Trip"') == {
            "action": "playlist_delete",
            "target": "Road Trip",
        }


# ── State Modifiers ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "cmd, expected",
    [
        ("volume 70", {"action": "set", "volume": 70.0}),
        ("mode shuffle", {"action": "set", "mode": "shuffle"}),
        ("mode repeat", {"action": "set", "mode": "repeat"}),
        ("mode normal", {"action": "set", "mode": "normal"}),
        ("mode SHUFFLE", {"action": "set", "mode": "shuffle"}),
        ('on "Living Room"', {"action": "set", "device": "Living Room"}),
        ('device "Bedroom"', {"action": "set", "device": "Bedroom"}),
    ],
)
def test_standalone_modifiers(cmd, expected):
    assert parse(cmd) == expected


class TestModifierComposition:
    def test_multiple_standalone(self):
        assert parse('volume 50 on "Bedroom"') == {
            "action": "set",
            "volume": 50.0,
            "device": "Bedroom",
        }

    def test_composed_with_play(self):
        assert parse('play "jazz" volume 70') == {
            "action": "play",
            "target": "jazz",
            "volume": 70.0,
        }

    def test_composed_with_play_multiple(self):
        assert parse('play "chill vibes" mode shuffle volume 50 on "Living Room"') == {
            "action": "play",
            "target": "chill vibes",
            "mode": "shuffle",
            "volume": 50.0,
            "device": "Living Room",
        }

    def test_composed_with_skip(self):
        assert parse("skip 2 volume 80") == {
            "action": "skip",
            "n": 2,
            "volume": 80.0,
        }

    def test_play_with_mode(self):
        assert parse("play spotify:playlist:abc123 mode shuffle") == {
            "action": "play",
            "target": "spotify:playlist:abc123",
            "mode": "shuffle",
        }


@pytest.mark.parametrize(
    "cmd, expected",
    [
        ("volume +10", {"action": "set", "volume_rel": 10}),
        ("volume -5", {"action": "set", "volume_rel": -5}),
        ('play "jazz" volume +10', {"action": "play", "target": "jazz", "volume_rel": 10}),
    ],
)
def test_volume_rel(cmd, expected):
    assert parse(cmd) == expected


# ── Queries ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "cmd, expected",
    [
        ('search "jazz"', {"query": "search", "term": "jazz"}),
        ('search "jazz" tracks', {"query": "search", "term": "jazz", "type": "tracks"}),
        ('search "jazz" artists', {"query": "search", "term": "jazz", "type": "artists"}),
        ('search "jazz" albums', {"query": "search", "term": "jazz", "type": "albums"}),
        ('search "lo-fi" playlists', {"query": "search", "term": "lo-fi", "type": "playlists"}),
        ('search "jazz" ARTISTS', {"query": "search", "term": "jazz", "type": "artists"}),
    ],
)
def test_search(cmd, expected):
    assert parse(cmd) == expected


@pytest.mark.parametrize(
    "cmd, expected",
    [
        ("now playing", {"query": "now_playing"}),
        ("get queue", {"query": "get_queue"}),
        ("get devices", {"query": "get_devices"}),
        ("library", {"query": "library"}),
        ("library artists", {"query": "library", "type": "artists"}),
        ("library tracks", {"query": "library", "type": "tracks"}),
        ("history", {"query": "history"}),
        ("info spotify:track:abc", {"query": "info", "target": "spotify:track:abc"}),
        ("info spotify:artist:abc", {"query": "info", "target": "spotify:artist:abc"}),
    ],
)
def test_simple_queries(cmd, expected):
    assert parse(cmd) == expected


class TestRecommend:
    def test_with_count(self):
        assert parse("recommend 5 for spotify:playlist:abc") == {
            "query": "recommend",
            "n": 5,
            "target": "spotify:playlist:abc",
        }

    def test_default_count(self):
        assert parse("recommend for spotify:playlist:abc") == {
            "query": "recommend",
            "target": "spotify:playlist:abc",
        }

    def test_string_target(self):
        assert parse('recommend 10 for "Road Trip"') == {
            "query": "recommend",
            "n": 10,
            "target": "Road Trip",
        }


# ── Query Modifiers ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "cmd, expected",
    [
        ('search "jazz" artists limit 5', {"query": "search", "term": "jazz", "type": "artists", "limit": 5}),
        ('search "rock" limit 20 offset 40', {"query": "search", "term": "rock", "limit": 20, "offset": 40}),
        ("library tracks limit 20 offset 40", {"query": "library", "type": "tracks", "limit": 20, "offset": 40}),
        ("history limit 10", {"query": "history", "limit": 10}),
    ],
)
def test_query_modifiers(cmd, expected):
    assert parse(cmd) == expected


# ── Grammar Enforcement ──────────────────────────────────────────


class TestGrammarEnforcement:
    def test_state_modifier_on_query_is_error(self):
        with pytest.raises(Exception):
            parse('search "jazz" volume 70')

    def test_query_modifier_on_action_is_error(self):
        with pytest.raises(Exception):
            parse('play "jazz" limit 5')

    def test_invalid_command(self):
        with pytest.raises(Exception):
            parse("explode everything")

    def test_empty_string(self):
        with pytest.raises(Exception):
            parse("")
