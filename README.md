# ytmusic-mcp

[![M8ven Score](https://m8ven.ai/badge/mcp/umsachde-commendation-19gofo)](https://m8ven.ai/mcp/umsachde-commendation-19gofo)

An [MCP](https://modelcontextprotocol.io) server that wraps [ytmusicapi](https://github.com/sigma67/ytmusicapi) so Claude (or any MCP client) can search YouTube Music, manage your playlists, and read your listening history.

## Tools

| Tool | Description |
| --- | --- |
| `search_music(query, filter=None, limit=20)` | Search YouTube Music. `filter` is one of `songs`, `videos`, `albums`, `artists`, `playlists`, `community_playlists`, `featured_playlists`, `profiles`, `podcasts`, `episodes`. |
| `get_playlists(limit=None)` | List your library playlists. Omit `limit` to fetch all of them. |
| `get_playlist_tracks(playlist_id, limit=None)` | Get the tracks in a playlist. Omit `limit` to fetch the entire playlist. |
| `create_playlist(name, description="")` | Create a new private playlist, returns its ID. |
| `add_to_playlist(playlist_id, video_id)` | Add a track to a playlist. |
| `remove_from_playlist(playlist_id, video_id)` | Remove every occurrence of a track from a playlist by video ID. |
| `remove_playlist(playlist_id)` | Permanently delete a playlist you own. Refuses to touch the auto playlists `LM` and `SE`. |
| `get_history()` | Get your recent play history. |
| `get_watch_playlist(video_id, limit=25, radio=True)` | Get the radio/autoplay queue for a song — one of two independent similarity signals. |
| `get_song_related(browse_id)` | Get "related content" sections for a song (the `browse_id` comes from `get_watch_playlist`'s `related` field) — the other independent similarity signal. |
| `get_artist(browse_id)` | Get an artist's page: top songs, albums, related artists. |
| `logout()` | Delete the local auth file, revoking this server's stored YouTube Music authorization. |

Other Claude Code projects on this machine (e.g. `re-com`) call these tools by spawning this server over MCP rather than talking to `ytmusicapi`/YouTube Music themselves — this is the only place YouTube Music credentials live.

**Not included (v1):** BPM-based recommendations. YouTube Music doesn't expose tempo data, so this would need a second data source (e.g. an audio analysis API) — a stretch goal for a future version, not part of this build.

## Setup

### 1. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Authenticate

There's no official YouTube Music API, so `ytmusicapi` authenticates by reusing headers from your logged-in browser session. Both methods below write the same `headers_auth.json` file, so you can switch between them freely.

#### Option A: Auto-extract from your browser (recommended)

Reads your existing YouTube Music session cookies straight from your browser's local storage — no DevTools, no copy-pasting.

```bash
pip install -e ".[browser-auth]"
python scripts/setup_auth_from_browser.py --browser firefox   # or chrome, safari, edge, brave, opera, vivaldi, arc
```

Requires being logged into [music.youtube.com](https://music.youtube.com) in that browser. Omit `--browser` to try every installed browser and use the first one with a valid session.

Notes:
- Chrome/Edge/Brave/Opera/Vivaldi/Arc encrypt their cookie store; on macOS this may trigger a one-time Keychain permission prompt.
- Some browsers lock their cookie database while running — close the browser first if extraction fails.

#### Option B: Manual header paste (fallback)

Use this if browser auto-extraction doesn't work for your setup.

1. Open [music.youtube.com](https://music.youtube.com) in **Firefox** (recommended — its raw-header copy is more reliable than Chrome's) while logged in.
2. Open DevTools (`Cmd+Option+I` / `F12`) → **Network** tab → filter by `browse`.
3. Click into a playlist, or reload the page, to trigger a `browse` POST request.
4. Click that request → **Headers** tab → toggle **Raw headers** → select and copy the whole block.
5. Paste it into a new file named `raw_headers.txt` in the project root and save.
6. Run:
   ```bash
   python scripts/setup_auth_from_file.py
   ```
   This writes `headers_auth.json` and deletes `raw_headers.txt`.

Alternatively, `python scripts/setup_auth.py` does the same thing via an interactive terminal prompt instead of a file, if you prefer to paste directly.

---

**`headers_auth.json` is equivalent to your logged-in session — never commit it or share it.** It's already gitignored.

Verify auth works before going further:

```bash
python scripts/test_search.py
```

These headers expire/rotate periodically. If tools start failing with an auth error, redo whichever setup option you used.

### 3. Add to Claude Code

```bash
claude mcp add ytmusic -s user \
  -e YTMUSIC_AUTH_PATH="$(pwd)/headers_auth.json" \
  -- "$(pwd)/.venv/bin/python" "$(pwd)/server.py"
```

`-s user` makes it available in any Claude Code session, not just this directory. Use absolute paths for the python interpreter, `server.py`, and `YTMUSIC_AUTH_PATH` since the server can be launched from any working directory.

For other MCP clients (Claude Desktop, etc.), point them at the same command and env var using their respective config format.

## Testing

The unit test suite (`tests/`) runs against a hand-rolled fake YTMusic client — no network access or `headers_auth.json` needed:

```bash
pip install -e ".[dev]"
pytest
```

`scripts/test_search.py` is a separate real-account smoke test, not part of the unit suite.

## Error handling

Tool calls translate common failure modes into clear messages instead of raw tracebacks:

- Missing/expired/malformed auth → tells you to redo the [authenticate step](#2-authenticate) (`scripts/setup_auth_from_browser.py` or `scripts/setup_auth_from_file.py`).
- Rate limiting (HTTP 429) → tells you to wait and retry.
- Gated/restricted content → reported as unavailable rather than crashing.
- Network errors → reported directly.

## License

MIT — see [LICENSE](LICENSE).
