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
    "Re-run scripts/setup_auth_from_file.py to refresh it (see README)."
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
                f"{AUTH_PATH} not found. Run scripts/setup_auth_from_file.py to authenticate."
            ) from e
        except json.JSONDecodeError as e:
            raise RuntimeError(f"YouTube Music returned an unexpected response. {AUTH_HELP}") from e
        except YTMusicServerError as e:
            msg = str(e)
            if "HTTP 401" in msg or "HTTP 403" in msg:
                raise RuntimeError(AUTH_HELP) from e
            if "HTTP 429" in msg:
                raise RuntimeError(
                    "YouTube Music is rate-limiting requests right now. Wait a bit and try again."
                ) from e
            raise RuntimeError(f"YouTube Music server error: {msg}") from e
        except YTMusicGatedError as e:
            raise RuntimeError(f"This content is gated/restricted and unavailable: {e}") from e
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
def get_playlists() -> list[dict[str, Any]]:
    """List your YouTube Music library playlists."""
    return _client().get_library_playlists()


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
def get_history() -> list[dict[str, Any]]:
    """Get recent play history."""
    return _client().get_history()


if __name__ == "__main__":
    mcp.run()
