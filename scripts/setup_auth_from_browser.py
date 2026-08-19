"""
Auto auth setup: read your already-logged-in browser's YouTube Music session
cookies directly from disk and write headers_auth.json, with no manual
DevTools copy-paste.

Requires you to be logged into https://music.youtube.com in the target
browser. Uses the same header format ytmusicapi's own `setup()` produces, so
the rest of the project (server.py, scripts/test_search.py) doesn't need to
know which setup script was used.

Usage:
    python scripts/setup_auth_from_browser.py [--browser chrome|firefox|safari|edge|brave|opera|vivaldi|arc]

If --browser is omitted, tries every supported browser installed on this
machine and uses the first one with a valid YouTube Music session.

Notes:
- Chrome/Edge/Brave/Opera/Vivaldi/Arc store cookies encrypted; on macOS this
  may trigger a one-time Keychain access prompt.
- Some browsers lock their cookie database while running -- close the
  browser first if extraction fails.

Writes ./headers_auth.json, which is gitignored and must never be committed
or shared -- it's equivalent to your logged-in session.
"""

import argparse
import json
import sys

import browser_cookie3
from ytmusicapi.constants import YTM_DOMAIN
from ytmusicapi.helpers import get_authorization, initialize_headers, sapisid_from_cookie

BROWSERS = {
    "chrome": browser_cookie3.chrome,
    "firefox": browser_cookie3.firefox,
    "safari": browser_cookie3.safari,
    "edge": browser_cookie3.edge,
    "brave": browser_cookie3.brave,
    "opera": browser_cookie3.opera,
    "vivaldi": browser_cookie3.vivaldi,
    "arc": browser_cookie3.arc,
}

OUT_PATH = "headers_auth.json"


def _load_cookies(browser: str | None):
    if browser:
        loaders = [(browser, BROWSERS[browser])]
    else:
        loaders = list(BROWSERS.items())

    errors = []
    for name, loader in loaders:
        try:
            cookiejar = loader(domain_name="youtube.com")
        except browser_cookie3.BrowserCookieError as e:
            errors.append(f"{name}: {e}")
            continue

        cookies = {c.name: c.value for c in cookiejar}
        if "__Secure-3PAPISID" in cookies:
            return name, cookies
        errors.append(f"{name}: no YouTube Music session cookie found (are you logged in?)")

    raise SystemExit(
        "Could not find a logged-in YouTube Music session in any browser.\n"
        + "\n".join(f"  - {e}" for e in errors)
        + "\n\nMake sure you're logged into https://music.youtube.com, then retry "
        "(closing the browser first if it locks its cookie database)."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", choices=sorted(BROWSERS), help="Browser to read cookies from.")
    args = parser.parse_args()

    browser_name, cookies = _load_cookies(args.browser)
    cookie_header = "; ".join(f"{name}={value}" for name, value in cookies.items())

    headers = initialize_headers()
    headers["cookie"] = cookie_header
    headers["x-goog-authuser"] = "0"

    sapisid = sapisid_from_cookie(cookie_header)
    headers["authorization"] = get_authorization(sapisid + " " + YTM_DOMAIN)

    with open(OUT_PATH, "w") as f:
        json.dump(dict(headers), f, ensure_ascii=True, indent=4, sort_keys=True)

    print(f"Saved auth to {OUT_PATH} (read from {browser_name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
