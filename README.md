# ytmusic-mcp

An [MCP](https://modelcontextprotocol.io) server that wraps [ytmusicapi](https://github.com/sigma67/ytmusicapi) so Claude (or any MCP client) can search YouTube Music, manage your playlists, and read your listening history.

## Tools

| Tool | Description |
| --- | --- |
| `search_music(query, filter=None, limit=20)` | Search YouTube Music. `filter` is one of `songs`, `videos`, `albums`, `artists`, `playlists`, `community_playlists`, `featured_playlists`, `profiles`, `podcasts`, `episodes`. |
| `get_playlists()` | List your library playlists. |
| `get_playlist_tracks(playlist_id)` | Get the tracks in a playlist. |
| `create_playlist(name, description="")` | Create a new private playlist, returns its ID. |
| `add_to_playlist(playlist_id, video_id)` | Add a track to a playlist. |
| `get_history()` | Get your recent play history. |

**Not included (v1):** BPM-based recommendations. YouTube Music doesn't expose tempo data, so this would need a second data source (e.g. an audio analysis API) — a stretch goal for a future version, not part of this build.

## Setup

### 1. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Authenticate

There's no official YouTube Music API, so `ytmusicapi` authenticates by reusing headers from your logged-in browser session.

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

**`headers_auth.json` is equivalent to your logged-in session — never commit it or share it.** It's already gitignored.

Verify auth works before going further:

```bash
python scripts/test_search.py
```

These headers expire/rotate periodically. If tools start failing with an auth error, redo this step.

### 3. Add to Claude Code

```bash
claude mcp add ytmusic -s user \
  -e YTMUSIC_AUTH_PATH="$(pwd)/headers_auth.json" \
  -- "$(pwd)/.venv/bin/python" "$(pwd)/server.py"
```

`-s user` makes it available in any Claude Code session, not just this directory. Use absolute paths for the python interpreter, `server.py`, and `YTMUSIC_AUTH_PATH` since the server can be launched from any working directory.

For other MCP clients (Claude Desktop, etc.), point them at the same command and env var using their respective config format.

## Error handling

Tool calls translate common failure modes into clear messages instead of raw tracebacks:

- Missing/expired/malformed auth → tells you to rerun `scripts/setup_auth_from_file.py`.
- Rate limiting (HTTP 429) → tells you to wait and retry.
- Gated/restricted content → reported as unavailable rather than crashing.
- Network errors → reported directly.

## License

MIT — see [LICENSE](LICENSE).
