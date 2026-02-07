"""Tests for the DSL parser — pure parsing, no network calls."""

import pytest
from clautify.dsl.parser import parse


# ── Playback Actions ──────────────────────────────────────────────


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

    def test_play_with_context(self):
        assert parse("play spotify:track:abc in spotify:playlist:def") == {
            "action": "play",
            "target": "spotify:track:abc",
            "context": "spotify:playlist:def",
        }

    def test_play_string_with_context(self):
        assert parse('play "Dark Side" in "Classic Rock"') == {
            "action": "play",
            "target": "Dark Side",
            "context": "Classic Rock",
        }


class TestPauseResume:
    def test_pause(self):
        assert parse("pause") == {"action": "pause"}

    def test_resume(self):
        assert parse("resume") == {"action": "resume"}


class TestSkip:
    def test_skip_default(self):
        assert parse("skip") == {"action": "skip", "n": 1}

    def test_skip_positive(self):
        assert parse("skip 3") == {"action": "skip", "n": 3}

    def test_skip_negative(self):
        assert parse("skip -1") == {"action": "skip", "n": -1}


class TestSeek:
    def test_seek(self):
        assert parse("seek 30000") == {"action": "seek", "position_ms": 30000.0}

    def test_seek_zero(self):
        assert parse("seek 0") == {"action": "seek", "position_ms": 0.0}


class TestQueue:
    def test_queue_uri(self):
        assert parse("queue spotify:track:abc123") == {
            "action": "queue",
            "target": "spotify:track:abc123",
        }

    def test_queue_string(self):
        assert parse('queue "Stairway to Heaven"') == {
            "action": "queue",
            "target": "Stairway to Heaven",
        }


# ── Library Actions ───────────────────────────────────────────────


class TestLikeUnlike:
    def test_like_uri(self):
        assert parse("like spotify:track:abc123") == {
            "action": "like",
            "target": "spotify:track:abc123",
        }

    def test_unlike_uri(self):
        assert parse("unlike spotify:track:abc123") == {
            "action": "unlike",
            "target": "spotify:track:abc123",
        }


class TestFollowUnfollow:
    def test_follow(self):
        assert parse("follow spotify:artist:abc123") == {
            "action": "follow",
            "target": "spotify:artist:abc123",
        }

    def test_unfollow(self):
        assert parse("unfollow spotify:artist:abc123") == {
            "action": "unfollow",
            "target": "spotify:artist:abc123",
        }


class TestSaveUnsave:
    def test_save(self):
        assert parse("save spotify:playlist:abc123") == {
            "action": "save",
            "target": "spotify:playlist:abc123",
        }

    def test_unsave(self):
        assert parse("unsave spotify:playlist:abc123") == {
            "action": "unsave",
            "target": "spotify:playlist:abc123",
        }


# ── Playlist Actions ──────────────────────────────────────────────


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


# ── State Modifiers ───────────────────────────────────────────────


class TestStateModifiers:
    def test_standalone_volume(self):
        assert parse("volume 70") == {"action": "set", "volume": 70.0}

    def test_standalone_mode_shuffle(self):
        assert parse("mode shuffle") == {"action": "set", "mode": "shuffle"}

    def test_standalone_mode_repeat(self):
        assert parse("mode repeat") == {"action": "set", "mode": "repeat"}

    def test_standalone_mode_normal(self):
        assert parse("mode normal") == {"action": "set", "mode": "normal"}

    def test_standalone_device(self):
        assert parse('on "Living Room"') == {"action": "set", "device": "Living Room"}

    def test_standalone_device_keyword(self):
        assert parse('device "Bedroom"') == {"action": "set", "device": "Bedroom"}

    def test_multiple_standalone_modifiers(self):
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


# ── Queries ───────────────────────────────────────────────────────


class TestSearch:
    def test_search_default(self):
        assert parse('search "taylor swift"') == {
            "query": "search",
            "term": "taylor swift",
        }

    def test_search_tracks(self):
        assert parse('search "jazz" tracks') == {
            "query": "search",
            "term": "jazz",
            "type": "tracks",
        }

    def test_search_artists(self):
        assert parse('search "jazz" artists') == {
            "query": "search",
            "term": "jazz",
            "type": "artists",
        }

    def test_search_albums(self):
        assert parse('search "jazz" albums') == {
            "query": "search",
            "term": "jazz",
            "type": "albums",
        }

    def test_search_playlists(self):
        assert parse('search "lo-fi" playlists') == {
            "query": "search",
            "term": "lo-fi",
            "type": "playlists",
        }


class TestOtherQueries:
    def test_now_playing(self):
        assert parse("now playing") == {"query": "now_playing"}

    def test_get_queue(self):
        assert parse("get queue") == {"query": "get_queue"}

    def test_get_devices(self):
        assert parse("get devices") == {"query": "get_devices"}

    def test_library(self):
        assert parse("library") == {"query": "library"}

    def test_library_artists(self):
        assert parse("library artists") == {"query": "library", "type": "artists"}

    def test_library_tracks(self):
        assert parse("library tracks") == {"query": "library", "type": "tracks"}

    def test_info_track(self):
        assert parse("info spotify:track:abc123") == {
            "query": "info",
            "target": "spotify:track:abc123",
        }

    def test_info_artist(self):
        assert parse("info spotify:artist:abc123") == {
            "query": "info",
            "target": "spotify:artist:abc123",
        }

    def test_history(self):
        assert parse("history") == {"query": "history"}


class TestRecommend:
    def test_recommend_with_count(self):
        assert parse("recommend 5 for spotify:playlist:abc123") == {
            "query": "recommend",
            "n": 5,
            "target": "spotify:playlist:abc123",
        }

    def test_recommend_default_count(self):
        assert parse("recommend for spotify:playlist:abc123") == {
            "query": "recommend",
            "target": "spotify:playlist:abc123",
        }

    def test_recommend_string_target(self):
        assert parse('recommend 10 for "Road Trip"') == {
            "query": "recommend",
            "n": 10,
            "target": "Road Trip",
        }


# ── Query Modifiers ───────────────────────────────────────────────


class TestQueryModifiers:
    def test_search_with_limit(self):
        assert parse('search "jazz" artists limit 5') == {
            "query": "search",
            "term": "jazz",
            "type": "artists",
            "limit": 5,
        }

    def test_search_with_limit_and_offset(self):
        assert parse('search "rock" limit 20 offset 40') == {
            "query": "search",
            "term": "rock",
            "limit": 20,
            "offset": 40,
        }

    def test_library_with_limit(self):
        assert parse("library tracks limit 20 offset 40") == {
            "query": "library",
            "type": "tracks",
            "limit": 20,
            "offset": 40,
        }

    def test_history_with_limit(self):
        assert parse("history limit 10") == {
            "query": "history",
            "limit": 10,
        }


# ── Grammar Enforcement ──────────────────────────────────────────


class TestGrammarEnforcement:
    def test_state_modifier_on_query_is_error(self):
        """State modifiers should NOT compose with queries."""
        with pytest.raises(Exception):
            parse('search "jazz" volume 70')

    def test_query_modifier_on_action_is_error(self):
        """Query modifiers should NOT compose with actions."""
        with pytest.raises(Exception):
            parse('play "jazz" limit 5')

    def test_invalid_command(self):
        with pytest.raises(Exception):
            parse("explode everything")

    def test_empty_string(self):
        with pytest.raises(Exception):
            parse("")


# ── Case Insensitivity ───────────────────────────────────────────


class TestCaseInsensitivity:
    def test_type_case_insensitive(self):
        assert parse('search "jazz" ARTISTS') == {
            "query": "search",
            "term": "jazz",
            "type": "artists",
        }

    def test_mode_case_insensitive(self):
        assert parse("mode SHUFFLE") == {"action": "set", "mode": "shuffle"}
