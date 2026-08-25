"""Unit tests for server.py.

Everything here runs against a hand-rolled fake YTMusic client -- no network,
no headers_auth.json required. This complements (does not replace)
scripts/test_search.py, which is a real-account smoke test.
"""

import json

import pytest
import requests
from ytmusicapi.exceptions import (
    YTMusicError,
    YTMusicGatedError,
    YTMusicServerError,
    YTMusicUserError,
)

import server
from server import (
    AUTH_HELP,
    AUTH_PATH,
    add_to_playlist,
    create_playlist,
    get_artist,
    get_history,
    get_playlist_tracks,
    get_playlists,
    get_lyrics,
    get_song_related,
    get_watch_playlist,
    handle_errors,
    remove_from_playlist,
    remove_playlist,
    search_music,
)


class _FakeYT:
    def __init__(
        self,
        search_results=None,
        library_playlists=None,
        playlists=None,
        history=None,
        create_playlist_result=None,
        watch_playlists=None,
        related_sections=None,
        artists=None,
        lyrics=None,
    ):
        self._search_results = search_results if search_results is not None else []
        self._library_playlists = library_playlists if library_playlists is not None else []
        self._playlists = playlists or {}
        self._history = history if history is not None else []
        self._create_playlist_result = create_playlist_result
        self._watch_playlists = watch_playlists or {}
        self._related_sections = related_sections or {}
        self._artists = artists or {}
        self._lyrics = lyrics or {}

        self.search_calls = []
        self.add_playlist_items_calls = []
        self.remove_playlist_items_calls = []
        self.delete_playlist_calls = []
        self.create_playlist_calls = []
        self.get_library_playlists_calls = []

    def search(self, query, filter=None, limit=20):
        self.search_calls.append((query, filter, limit))
        result = self._search_results
        if isinstance(result, Exception):
            raise result
        return result

    def get_library_playlists(self, limit=25):
        self.get_library_playlists_calls.append(limit)
        result = self._library_playlists
        if isinstance(result, Exception):
            raise result
        return result

    def get_watch_playlist(self, videoId=None, limit=25, radio=False):
        result = self._watch_playlists[videoId]
        if isinstance(result, Exception):
            raise result
        return result

    def get_song_related(self, browseId):
        result = self._related_sections[browseId]
        if isinstance(result, Exception):
            raise result
        return result

    def get_lyrics(self, browseId):
        result = self._lyrics[browseId]
        if isinstance(result, Exception):
            raise result
        return result

    def get_artist(self, channelId):
        result = self._artists[channelId]
        if isinstance(result, Exception):
            raise result
        return result

    def get_playlist(self, playlist_id, limit=None):
        result = self._playlists[playlist_id]
        if isinstance(result, Exception):
            raise result
        return result

    def create_playlist(self, name, description):
        self.create_playlist_calls.append((name, description))
        result = self._create_playlist_result
        if isinstance(result, Exception):
            raise result
        return result

    def add_playlist_items(self, playlist_id, video_ids):
        self.add_playlist_items_calls.append((playlist_id, video_ids))
        return {"status": "STATUS_SUCCEEDED"}

    def remove_playlist_items(self, playlist_id, tracks):
        self.remove_playlist_items_calls.append((playlist_id, tracks))

    def delete_playlist(self, playlistId):
        self.delete_playlist_calls.append(playlistId)
        result = self._playlists.get(f"__delete__{playlistId}", "STATUS_SUCCEEDED")
        if isinstance(result, Exception):
            raise result
        return result

    def get_history(self):
        result = self._history
        if isinstance(result, Exception):
            raise result
        return result


# --- search_music ----------------------------------------------------------


def test_search_music_passes_through(monkeypatch):
    yt = _FakeYT(search_results=[{"videoId": "v1", "title": "Song"}])
    monkeypatch.setattr(server, "_client", lambda: yt)

    results = search_music("some query", filter="songs", limit=5)

    assert results == [{"videoId": "v1", "title": "Song"}]
    assert yt.search_calls == [("some query", "songs", 5)]


# --- get_playlists / get_playlist_tracks ------------------------------------


def test_get_playlists_passes_through(monkeypatch):
    yt = _FakeYT(library_playlists=[{"playlistId": "PL1", "title": "My Playlist"}])
    monkeypatch.setattr(server, "_client", lambda: yt)

    assert get_playlists() == [{"playlistId": "PL1", "title": "My Playlist"}]


def test_get_playlists_defaults_to_no_limit(monkeypatch):
    yt = _FakeYT()
    monkeypatch.setattr(server, "_client", lambda: yt)

    get_playlists()

    assert yt.get_library_playlists_calls == [None]


def test_get_playlists_passes_explicit_limit(monkeypatch):
    yt = _FakeYT()
    monkeypatch.setattr(server, "_client", lambda: yt)

    get_playlists(limit=5)

    assert yt.get_library_playlists_calls == [5]


def test_get_playlist_tracks_returns_tracks(monkeypatch):
    yt = _FakeYT(playlists={"PL1": {"tracks": [{"videoId": "v1"}, {"videoId": "v2"}]}})
    monkeypatch.setattr(server, "_client", lambda: yt)

    assert get_playlist_tracks("PL1") == [{"videoId": "v1"}, {"videoId": "v2"}]


def test_get_playlist_tracks_missing_tracks_key_returns_empty(monkeypatch):
    yt = _FakeYT(playlists={"PL1": {}})
    monkeypatch.setattr(server, "_client", lambda: yt)

    assert get_playlist_tracks("PL1") == []


# --- create_playlist ---------------------------------------------------------


def test_create_playlist_returns_id(monkeypatch):
    yt = _FakeYT(create_playlist_result="PL_NEW_ID")
    monkeypatch.setattr(server, "_client", lambda: yt)

    result = create_playlist("My New Playlist", "a description")

    assert result == "PL_NEW_ID"
    assert yt.create_playlist_calls == [("My New Playlist", "a description")]


def test_create_playlist_dict_result_raises(monkeypatch):
    # ytmusicapi returns a dict instead of a string ID when creation fails.
    yt = _FakeYT(create_playlist_result={"error": "something went wrong"})
    monkeypatch.setattr(server, "_client", lambda: yt)

    with pytest.raises(RuntimeError, match="Failed to create playlist"):
        create_playlist("My New Playlist")


# --- add_to_playlist / remove_from_playlist ---------------------------------


def test_add_to_playlist(monkeypatch):
    yt = _FakeYT()
    monkeypatch.setattr(server, "_client", lambda: yt)

    add_to_playlist("PL1", "v1")

    assert yt.add_playlist_items_calls == [("PL1", ["v1"])]


def test_remove_from_playlist_removes_all_occurrences(monkeypatch):
    yt = _FakeYT(
        playlists={
            "PL1": {
                "tracks": [
                    {"videoId": "v1", "setVideoId": "s1"},
                    {"videoId": "v2", "setVideoId": "s2"},
                    {"videoId": "v1", "setVideoId": "s3"},
                ]
            }
        }
    )
    monkeypatch.setattr(server, "_client", lambda: yt)

    result = remove_from_playlist("PL1", "v1")

    assert result == "Removed 2 occurrence(s) of v1 from playlist PL1."
    [(playlist_id, tracks)] = yt.remove_playlist_items_calls
    assert playlist_id == "PL1"
    assert {t["setVideoId"] for t in tracks} == {"s1", "s3"}


def test_remove_from_playlist_not_found_is_a_no_op(monkeypatch):
    yt = _FakeYT(playlists={"PL1": {"tracks": [{"videoId": "v2"}]}})
    monkeypatch.setattr(server, "_client", lambda: yt)

    result = remove_from_playlist("PL1", "v1")

    assert result == "v1 was not found in playlist PL1; nothing removed."
    assert yt.remove_playlist_items_calls == []


# --- remove_playlist ---------------------------------------------------------


def test_remove_playlist_deletes(monkeypatch):
    yt = _FakeYT()
    monkeypatch.setattr(server, "_client", lambda: yt)

    result = remove_playlist("PL1")

    assert result == "STATUS_SUCCEEDED"
    assert yt.delete_playlist_calls == ["PL1"]


def test_remove_playlist_refuses_liked_music(monkeypatch):
    yt = _FakeYT()
    monkeypatch.setattr(server, "_client", lambda: yt)

    with pytest.raises(RuntimeError, match="auto playlist"):
        remove_playlist("LM")

    assert yt.delete_playlist_calls == []


def test_remove_playlist_refuses_episodes_for_later(monkeypatch):
    yt = _FakeYT()
    monkeypatch.setattr(server, "_client", lambda: yt)

    with pytest.raises(RuntimeError, match="auto playlist"):
        remove_playlist("SE")

    assert yt.delete_playlist_calls == []


# --- get_history ---------------------------------------------------------


def test_get_history_passes_through(monkeypatch):
    yt = _FakeYT(history=[{"videoId": "v1", "title": "Recently Played"}])
    monkeypatch.setattr(server, "_client", lambda: yt)

    assert get_history() == [{"videoId": "v1", "title": "Recently Played"}]


# --- get_watch_playlist / get_song_related / get_artist ---------------------


def test_get_watch_playlist_passes_through(monkeypatch):
    yt = _FakeYT(watch_playlists={"v1": {"tracks": [{"videoId": "v2"}], "related": "REL1"}})
    monkeypatch.setattr(server, "_client", lambda: yt)

    assert get_watch_playlist("v1") == {"tracks": [{"videoId": "v2"}], "related": "REL1"}


def test_get_watch_playlist_missing_raises(monkeypatch):
    yt = _FakeYT(watch_playlists={"v1": YTMusicError("gone")})
    monkeypatch.setattr(server, "_client", lambda: yt)

    with pytest.raises(RuntimeError, match="YouTube Music error"):
        get_watch_playlist("v1")


def test_get_song_related_passes_through(monkeypatch):
    yt = _FakeYT(related_sections={"REL1": [{"contents": [{"videoId": "v3"}]}]})
    monkeypatch.setattr(server, "_client", lambda: yt)

    assert get_song_related("REL1") == [{"contents": [{"videoId": "v3"}]}]


def test_get_lyrics_passes_through(monkeypatch):
    yt = _FakeYT(lyrics={"LYR1": {"lyrics": "some words", "source": "Musixmatch"}})
    monkeypatch.setattr(server, "_client", lambda: yt)

    assert get_lyrics("LYR1") == {"lyrics": "some words", "source": "Musixmatch"}


def test_get_lyrics_reports_a_failure_cleanly(monkeypatch):
    yt = _FakeYT(lyrics={"LYR1": YTMusicError("nope")})
    monkeypatch.setattr(server, "_client", lambda: yt)

    with pytest.raises(RuntimeError, match="YouTube Music error"):
        get_lyrics("LYR1")


def test_get_artist_passes_through(monkeypatch):
    yt = _FakeYT(artists={"UC1": {"name": "Some Artist", "songs": {"results": []}}})
    monkeypatch.setattr(server, "_client", lambda: yt)

    assert get_artist("UC1") == {"name": "Some Artist", "songs": {"results": []}}


# --- handle_errors -------------------------------------------------------


def test_handle_errors_passes_through_success():
    @handle_errors
    def fn():
        return 42

    assert fn() == 42


def test_handle_errors_file_not_found():
    @handle_errors
    def fn():
        raise FileNotFoundError()

    with pytest.raises(RuntimeError, match="setup_auth_from_browser.py"):
        fn()
    with pytest.raises(RuntimeError, match=AUTH_PATH.replace(".", r"\.")):
        fn()


def test_handle_errors_json_decode_error():
    @handle_errors
    def fn():
        raise json.JSONDecodeError("bad", "doc", 0)

    with pytest.raises(RuntimeError, match="unexpected response"):
        fn()


def test_handle_errors_server_error_401_maps_to_auth_help():
    @handle_errors
    def fn():
        raise YTMusicServerError("HTTP 401 Unauthorized")

    with pytest.raises(RuntimeError, match=AUTH_HELP.split(".")[0]):
        fn()


def test_handle_errors_server_error_403_maps_to_auth_help():
    @handle_errors
    def fn():
        raise YTMusicServerError("HTTP 403 Forbidden")

    with pytest.raises(RuntimeError, match=AUTH_HELP.split(".")[0]):
        fn()


def test_handle_errors_server_error_429_maps_to_rate_limit_message():
    @handle_errors
    def fn():
        raise YTMusicServerError("HTTP 429 Too Many Requests")

    with pytest.raises(RuntimeError, match="rate-limiting"):
        fn()


def test_handle_errors_other_server_error():
    @handle_errors
    def fn():
        raise YTMusicServerError("HTTP 500 Internal Server Error")

    with pytest.raises(RuntimeError, match="YouTube Music server error"):
        fn()


def test_handle_errors_gated_error():
    @handle_errors
    def fn():
        raise YTMusicGatedError("interaction required")

    with pytest.raises(RuntimeError, match="gated/restricted"):
        fn()


def test_handle_errors_user_error():
    @handle_errors
    def fn():
        raise YTMusicUserError("bad usage")

    with pytest.raises(RuntimeError, match="bad usage"):
        fn()


def test_handle_errors_generic_ytmusic_error():
    @handle_errors
    def fn():
        raise YTMusicError("something else")

    with pytest.raises(RuntimeError, match="YouTube Music error"):
        fn()


def test_handle_errors_network_error():
    @handle_errors
    def fn():
        raise requests.exceptions.ConnectionError("no route to host")

    with pytest.raises(RuntimeError, match="Network error"):
        fn()
