"""
Standalone smoke test: confirms headers_auth.json works before we
touch the MCP layer at all.

    python scripts/test_search.py
"""

import sys

from ytmusicapi import YTMusic


def main() -> int:
    try:
        yt = YTMusic("headers_auth.json")
    except Exception as e:
        print(f"Failed to load headers_auth.json: {e}")
        print("Run scripts/setup_auth.py first.")
        return 1

    results = yt.search("Daft Punk", filter="songs", limit=5)
    if not results:
        print("Auth loaded, but search returned no results -- something's off.")
        return 1

    print(f"Auth OK. Top {len(results)} results for 'Daft Punk':")
    for r in results:
        title = r.get("title")
        artists = ", ".join(a["name"] for a in r.get("artists") or [])
        print(f"  - {title} — {artists}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
