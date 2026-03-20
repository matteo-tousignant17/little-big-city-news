"""
auth_setup.py — One-time local script to capture a beehiiv login session.

Run this locally whenever you need to (re)authenticate:

    python auth_setup.py

A real Chromium browser window opens. Log in to beehiiv using whatever
method you use (Google, Apple, email+password, etc.). Once you see the
beehiiv dashboard, come back here and press Enter.

The script saves your session to auth_state.json (gitignored) and prints
a base64 value to add as the BEEHIIV_AUTH_STATE GitHub Secret.

Sessions typically last weeks to months. Re-run this script when the
GitHub Actions workflow logs show "beehiiv session expired".
"""

import base64
import json
import sys

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("ERROR: playwright is not installed.")
    print("Run: pip install playwright && playwright install chromium")
    sys.exit(1)


def main():
    print("=" * 60)
    print("beehiiv Auth Setup")
    print("=" * 60)
    print()
    print("Opening beehiiv login in a browser window...")
    print("Log in using Google (or any method you normally use).")
    print()

    with sync_playwright() as p:
        # Must be visible (headless=False) — Google OAuth blocks headless browsers
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        page.goto("https://app.beehiiv.com/login", wait_until="domcontentloaded")

        print("Waiting for you to log in...")
        print("Once you see the beehiiv dashboard, press Enter here.")
        input()

        # Capture all cookies and localStorage for the logged-in session
        state = context.storage_state()
        browser.close()

    # Save locally (for local development runs)
    auth_file = "auth_state.json"
    with open(auth_file, "w") as f:
        json.dump(state, f)
    print(f"\nSession saved to {auth_file} (gitignored, used for local runs)")

    # Encode as base64 for GitHub Secret
    b64 = base64.b64encode(json.dumps(state).encode()).decode()

    print()
    print("=" * 60)
    print("Add the following as GitHub Secret BEEHIIV_AUTH_STATE:")
    print("  Repo → Settings → Secrets and variables → Actions → New secret")
    print("=" * 60)
    print()
    print(b64)
    print()
    print("=" * 60)
    print("Done! The pipeline will use this session until it expires.")
    print("Re-run this script if the workflow logs show 'session expired'.")


if __name__ == "__main__":
    main()
