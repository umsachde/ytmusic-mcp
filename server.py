"""MCP server exposing YouTube Music (via ytmusicapi) as tools for Claude."""

import functools
import json
import os
from typing import Any

import requests
from mcp.server.mcpserver import MCPServer
from ytmusicapi import YTMusic
from ytmusicapi.exceptions import YTMusicError, YTMusicGatedError, YTMusicServerError, YTMusicUserError

AUTH_PATH = os.environ.get("YTMUSIC_AUTH_PATH", "headers_auth.json")
AUTH_HELP = (
    f"YouTube Music auth at {AUTH_PATH} looks invalid or expired. "
    "Re-run scripts/setup_auth_from_browser.py (or scripts/setup_auth_from_file.py) to refresh it (see README)."
)

mcp = MCPServer("ytmusic")

_yt: YTMusic | None = None


def _client() -> YTMusic:
    global _yt
    if _yt is None:
        _yt = YTMusic(AUTH_PATH)
    return _yt


def handle_errors(fn):
    """Translate ytmusicapi/network failures into clear, actionable messages.

    Expired or malformed auth headers don't always raise a typed exception --
    a bad session can make YouTube's frontend return an HTML error page where
    ytmusicapi expects JSON, which surfaces as a raw JSONDecodeError.
    """

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except FileNotFoundError as e:
            raise RuntimeError(
                f"{AUTH_PATH} not found. Run scripts/setup_auth_from_browser.py to authenticate."
            ) from e
        except json.JSONDecodeError as e:
            raise RuntimeError(f"YouTube Music returned an unexpected response. {AUTH_HELP}") from e
        except YTMusicGatedError as e:
            raise RuntimeError(f"This content is gated/restricted and unavailable: {e}") from e
        except YTMusicServerError as e:
            msg = str(e)
            if "HTTP 401" in msg or "HTTP 403" in msg:
                raise RuntimeError(AUTH_HELP) from e
            if "HTTP 429" in msg:
                raise RuntimeError(
                    "YouTube Music is rate-limiting requests right now. Wait a bit and try again."
                ) from e
            raise RuntimeError(f"YouTube Music server error: {msg}") from e
        except YTMusicUserError as e:
            raise RuntimeError(str(e)) from e
        except YTMusicError as e:
            raise RuntimeError(f"YouTube Music error: {e}") from e
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Network error reaching YouTube Music: {e}") from e

    return wrapper


@mcp.tool()
@handle_errors
def search_music(query: str, filter: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """Search YouTube Music.

    filter: one of songs, videos, albums, artists, playlists, community_playlists,
    featured_playlists, profiles, podcasts, episodes. Omit for a mixed search.
    Returns an empty list if there are no matches.
    """
    return _client().search(query, filter=filter, limit=limit)


@mcp.tool()
@handle_errors
def get_playlists(limit: int | None = None) -> list[dict[str, Any]]:
    """List your YouTube Music library playlists.

    limit: max playlists to return. Omit (or pass null) to fetch all of them.
    """
    return _client().get_library_playlists(limit=limit)


@mcp.tool()
@handle_errors
def get_playlist_tracks(playlist_id: str, limit: int | None = None) -> list[dict[str, Any]]:
    """Get the tracks in a playlist.

    limit: max tracks to return. Omit (or pass null) to fetch the entire playlist.
    """
    return _client().get_playlist(playlist_id, limit=limit).get("tracks", [])


@mcp.tool()
@handle_errors
def create_playlist(name: str, description: str = "") -> str:
    """Create a new private playlist and return its playlist ID."""
    result = _client().create_playlist(name, description)
    if isinstance(result, dict):
        raise RuntimeError(f"Failed to create playlist: {result}")
    return result


@mcp.tool()
@handle_errors
def add_to_playlist(playlist_id: str, video_id: str) -> str:
    """Add a track to a playlist by video ID."""
    return str(_client().add_playlist_items(playlist_id, [video_id]))


@mcp.tool()
@handle_errors
def remove_from_playlist(playlist_id: str, video_id: str) -> str:
    """Remove every occurrence of a track from a playlist by video ID.

    Looks up the playlist entry (or entries, if the song was added more than
    once) internally, so only the video ID is needed. Returns a message
    stating how many occurrences were removed -- 0 if the video ID wasn't in
    the playlist.
    """
    yt = _client()
    tracks = yt.get_playlist(playlist_id, limit=None).get("tracks", [])
    matches = [t for t in tracks if t.get("videoId") == video_id]
    if not matches:
        return f"{video_id} was not found in playlist {playlist_id}; nothing removed."
    yt.remove_playlist_items(playlist_id, matches)
    return f"Removed {len(matches)} occurrence(s) of {video_id} from playlist {playlist_id}."


@mcp.tool()
@handle_errors
def remove_playlist(playlist_id: str) -> str:
    """Permanently delete a playlist you own.

    This cannot be undone -- the playlist itself is removed from your
    YouTube Music library, not just emptied. Does not affect the songs
    inside it (they aren't deleted, just no longer grouped under this
    playlist). Refuses to touch the auto playlists "LM" (Liked Music) and
    "SE" (Episodes for Later), which aren't deletable playlists.
    """
    if playlist_id in ("LM", "SE"):
        raise RuntimeError(f"{playlist_id} is an auto playlist and can't be deleted.")
    return str(_client().delete_playlist(playlist_id))


@mcp.tool()
def logout() -> str:
    """Delete the stored YouTube Music authorization.

    Removes the local auth file (headers_auth.json by default, or
    YTMUSIC_AUTH_PATH if set) and clears the cached client. Subsequent
    tool calls will fail until you re-authenticate via
    scripts/setup_auth_from_browser.py (or setup_auth_from_file.py).
    """
    global _yt
    if not os.path.exists(AUTH_PATH):
        return f"No auth file found at {AUTH_PATH}; nothing to remove."
    os.remove(AUTH_PATH)
    _yt = None
    return f"Removed {AUTH_PATH}. Re-run scripts/setup_auth_from_browser.py to authenticate again."


@mcp.tool()
@handle_errors
def get_history() -> list[dict[str, Any]]:
    """Get recent play history."""
    return _client().get_history()


@mcp.tool()
@handle_errors
def get_watch_playlist(video_id: str, limit: int = 25, radio: bool = True) -> dict[str, Any]:
    """Get the watch-next queue for a song -- its radio/autoplay tracks.

    Returns a dict with a "tracks" list and a "related" browse ID (feed it to
    get_song_related for a second, independently-generated set of similar
    songs). radio=True (the default) requests the radio-mix ordering rather
    than a plain queue.
    """
    return _client().get_watch_playlist(videoId=video_id, limit=limit, radio=radio)


@mcp.tool()
@handle_errors
def get_song_related(browse_id: str) -> list[dict[str, Any]]:
    """Get "related content" sections for a song -- the browse ID for this
    comes from get_watch_playlist's "related" field.

    Distinct from get_watch_playlist's radio: a separate, independently
    generated similarity signal.
    """
    return _client().get_song_related(browse_id)


@mcp.tool()
@handle_errors
def get_artist(browse_id: str) -> dict[str, Any]:
    """Get an artist's page: top songs, albums, and related artists.

    browse_id is the artist's channel ID, e.g. from a search result's or a
    track's "artists" entry.
    """
    return _client().get_artist(browse_id)


if __name__ == "__main__":
    mcp.run()
