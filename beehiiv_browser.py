"""
beehiiv_browser.py — Playwright browser-based publishing for What's Up [CITY].

Publishes newsletter posts to beehiiv using a saved login session — no password
or paid API tier required. Supports any login method (Google, Apple, email, etc.).

Authentication:
  - In CI: reads BEEHIIV_AUTH_STATE env var (base64-encoded Playwright storage state)
  - Locally: reads auth_state.json in the project root
  - To generate/refresh: python auth_setup.py

Requires: playwright>=1.40.0
Install Chromium: playwright install chromium
"""

import base64
import json
import logging
import os
import re
from datetime import datetime

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)

_TIMEOUT = 20_000  # ms — per-action timeout


def publish_via_browser(
    publication_id: str,
    title: str,
    subject: str,
    html_content: str,
    scheduled_at: str | None = None,
    headless: bool = True,
) -> dict:
    """
    Create and optionally schedule a beehiiv newsletter post via browser automation.

    Uses a saved Playwright auth session (BEEHIIV_AUTH_STATE env var or auth_state.json)
    so no password is needed and any login method (Google OAuth, etc.) is supported.

    Args:
        publication_id: beehiiv pub_xxx... from cities/<slug>/config.json
        title: Internal post name shown in the beehiiv dashboard
        subject: Email subject line shown to subscribers
        html_content: Complete HTML body of the newsletter
        scheduled_at: UTC ISO 8601 timestamp for scheduled send (None = save as draft)
        headless: True for CI/GitHub Actions; False for local debugging

    Returns:
        {"success": bool, "post_url": str | None, "error": str | None}
    """
    auth_state = _load_auth_state()
    if not auth_state:
        return {
            "success": False,
            "post_url": None,
            "error": (
                "No beehiiv auth state found. "
                "Run: python auth_setup.py — then add BEEHIIV_AUTH_STATE as a GitHub Secret."
            ),
        }

    result: dict = {"success": False, "post_url": None, "error": None}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            storage_state=auth_state,
            viewport={"width": 1440, "height": 900},
            permissions=["clipboard-read", "clipboard-write"],
        )
        page = context.new_page()

        try:
            post_url = _create_post(
                page, publication_id, title, subject, html_content, scheduled_at
            )
            result["success"] = True
            result["post_url"] = post_url
            logger.info(f"beehiiv post created via browser: {post_url}")

        except PlaywrightTimeout as e:
            msg = f"Timed out waiting for beehiiv UI element: {e}"
            logger.error(msg)
            result["error"] = msg
            _screenshot(page, "beehiiv_timeout")

        except Exception as e:
            msg = f"beehiiv browser automation failed: {e}"
            logger.error(msg)
            result["error"] = msg
            _screenshot(page, "beehiiv_error")

        finally:
            browser.close()

    return result


# ─── Auth State ───────────────────────────────────────────────────────────────

def _load_auth_state() -> dict | None:
    """
    Load Playwright storage state (cookies + localStorage) for the beehiiv session.

    Priority:
    1. BEEHIIV_AUTH_STATE env var — base64-encoded JSON (used in GitHub Actions)
    2. auth_state.json file in project root (used for local development)
    """
    b64 = os.getenv("BEEHIIV_AUTH_STATE", "")
    if b64:
        try:
            return json.loads(base64.b64decode(b64).decode())
        except Exception as e:
            logger.error(f"Failed to decode BEEHIIV_AUTH_STATE: {e}")
            return None

    if os.path.exists("auth_state.json"):
        with open("auth_state.json") as f:
            return json.load(f)

    return None


# ─── Create Post ──────────────────────────────────────────────────────────────

def _create_post(
    page,
    publication_id: str,
    title: str,
    subject: str,
    html_content: str,
    scheduled_at: str | None,
) -> str:
    """Open new post editor, populate all fields, save/schedule. Returns final page URL."""
    new_post_url = f"https://app.beehiiv.com/publications/{publication_id}/posts/new"
    logger.info(f"Opening new post editor: {new_post_url}")
    page.goto(new_post_url, wait_until="domcontentloaded", timeout=30_000)

    # Detect expired/invalid session — beehiiv redirects to /login if not authenticated
    if "/login" in page.url:
        raise RuntimeError(
            "beehiiv session expired or invalid. "
            "Re-run: python auth_setup.py — then update the BEEHIIV_AUTH_STATE GitHub Secret."
        )

    logger.info("beehiiv session restored from auth state")

    # Wait for the React editor to fully initialise
    page.wait_for_load_state("networkidle", timeout=30_000)
    page.wait_for_timeout(2000)

    _set_title(page, title)
    _insert_html_block(page, html_content)
    _set_subject(page, subject)

    if scheduled_at:
        logger.info(f"Scheduling post for {scheduled_at}...")
        _schedule_post(page, scheduled_at)
        logger.info("Post scheduled")
    else:
        _save_draft(page)
        logger.info("Post saved as draft")

    return page.url


# ─── Step: Set Title ──────────────────────────────────────────────────────────

def _set_title(page, title: str) -> None:
    """Click the post title area and type the internal title."""
    logger.info("Setting post title...")
    # beehiiv shows a large placeholder heading ("Untitled") at the top of the editor
    selectors = [
        '[data-placeholder="Untitled"]',
        '[placeholder="Untitled"]',
        'h1[contenteditable]',
        'input[name="title"]',
    ]
    for sel in selectors:
        loc = page.locator(sel).first
        if loc.count() > 0:
            loc.click()
            tag = loc.evaluate("el => el.tagName.toLowerCase()")
            if tag == "input":
                loc.fill(title)
            else:
                page.keyboard.press("Control+a")
                page.keyboard.type(title)
            return

    # Last resort: type into whichever contenteditable the cursor lands in
    page.locator('[contenteditable="true"]').first.click()
    page.keyboard.press("Control+a")
    page.keyboard.type(title)


# ─── Step: Insert Custom HTML Block ──────────────────────────────────────────

def _insert_html_block(page, html_content: str) -> None:
    """
    Add a Custom HTML block to the post body and fill it with newsletter HTML.

    Uses beehiiv's slash-command system: typing "/html" in the editor opens
    a block picker filtered to the Custom HTML option.
    """
    logger.info("Inserting Custom HTML block...")

    # Position cursor in the editor body
    editor = page.locator('[contenteditable="true"]').last
    editor.click()
    page.keyboard.press("End")
    page.keyboard.press("Enter")

    # Slash command: opens block picker
    page.keyboard.type("/html")
    page.wait_for_timeout(600)

    # Select the "Custom HTML" option from the block picker
    html_picked = False
    for role in ("option", "menuitem", "listitem"):
        opt = page.get_by_role(role, name=re.compile(r"html", re.I)).first  # type: ignore[call-arg]
        if opt.count() > 0:
            opt.click()
            html_picked = True
            break

    if not html_picked:
        opt = page.locator('[role="option"], [role="menuitem"]').filter(
            has_text=re.compile(r"html", re.I)
        ).first
        if opt.count() > 0:
            opt.click()
            html_picked = True

    if not html_picked:
        raise RuntimeError(
            "Could not find 'Custom HTML' in beehiiv block picker. "
            "The slash-command '/html' did not produce a selectable option."
        )

    page.wait_for_timeout(800)
    _fill_html_editor(page, html_content)


def _fill_html_editor(page, html_content: str) -> None:
    """
    Fill the custom HTML block's code editor with content.

    Tries, in order:
    1. CodeMirror 5 (cm.CodeMirror.setValue)
    2. CodeMirror 6 (dispatch transaction)
    3. Plain <textarea> via fill()
    Uses page.evaluate() to avoid the slowness of keyboard.type() for large HTML.
    """
    filled = page.evaluate(
        """(html) => {
            // CodeMirror 5
            const cm5 = document.querySelector('.CodeMirror');
            if (cm5 && cm5.CodeMirror) {
                cm5.CodeMirror.setValue(html);
                return 'cm5';
            }
            // CodeMirror 6
            const cm6 = document.querySelector('.cm-editor');
            if (cm6) {
                const view = cm6.cmView || cm6.__cmView;
                if (view) {
                    view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: html } });
                    return 'cm6';
                }
            }
            // Plain textarea
            const ta = document.querySelector('textarea:not([style*="display: none"])');
            if (ta) {
                ta.value = html;
                ta.dispatchEvent(new Event('input', { bubbles: true }));
                ta.dispatchEvent(new Event('change', { bubbles: true }));
                return 'textarea';
            }
            return null;
        }""",
        html_content,
    )

    if filled:
        logger.info(f"HTML content filled via {filled} editor")
    else:
        # Clipboard fallback for large content
        logger.warning("JS editor injection failed; attempting clipboard paste")
        page.evaluate("(html) => navigator.clipboard.writeText(html)", html_content)
        page.keyboard.press("Control+a")
        page.keyboard.press("Control+v")

    page.wait_for_timeout(400)

    # Click Save/Apply/Done button inside the block modal if present
    for btn_name in ("Save", "Apply", "Done", "Update", "Insert"):
        btn = page.get_by_role("button", name=btn_name)
        if btn.count() > 0 and btn.first.is_visible():
            btn.first.click()
            page.wait_for_timeout(400)
            logger.info(f"Clicked '{btn_name}' to confirm HTML block")
            break


# ─── Step: Set Email Subject ──────────────────────────────────────────────────

def _set_subject(page, subject: str) -> None:
    """
    Open the beehiiv email settings panel and set the subject line.

    beehiiv keeps email-specific settings (subject, preview text) in a sidebar
    panel accessed via an "Email" tab or gear icon in the post editor.
    """
    logger.info("Setting email subject line...")

    # Try to open the email settings panel
    for label in (
        re.compile(r"email\s*settings", re.I),
        re.compile(r"^email$", re.I),
        re.compile(r"settings", re.I),
    ):
        btn = page.get_by_role("button", name=label).first
        if btn.count() > 0 and btn.is_visible():
            btn.click()
            page.wait_for_timeout(400)
            break
    else:
        tab = page.get_by_role("tab", name=re.compile(r"email", re.I)).first
        if tab.count() > 0:
            tab.click()
            page.wait_for_timeout(400)

    # Fill in subject line — try by label, then by placeholder
    subject_loc = page.get_by_label(re.compile(r"subject", re.I)).first
    if subject_loc.count() == 0:
        subject_loc = page.get_by_placeholder(re.compile(r"subject", re.I)).first

    subject_loc.wait_for(state="visible", timeout=_TIMEOUT)
    subject_loc.fill(subject)
    logger.info(f"Subject set: {subject}")


# ─── Step: Schedule ───────────────────────────────────────────────────────────

def _schedule_post(page, scheduled_at: str) -> None:
    """
    Click the Publish/Schedule button and set the scheduled send time.

    scheduled_at is a UTC ISO 8601 timestamp (e.g. "2026-03-27T14:00:00+00:00").
    """
    dt = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))

    # Click the main publish/schedule button (top-right of editor)
    publish_btn = page.get_by_role(
        "button", name=re.compile(r"publish|schedule|send", re.I)
    ).first
    publish_btn.click()
    page.wait_for_timeout(500)

    # If a dropdown appeared, choose "Schedule" option
    schedule_opt = page.get_by_role("menuitem", name=re.compile(r"schedule", re.I)).first
    if schedule_opt.count() > 0:
        schedule_opt.click()
        page.wait_for_timeout(500)

    # Fill date/time fields if a scheduling modal opened
    def _fill_if_visible(selectors: list[str], value: str) -> None:
        for sel in selectors:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible():
                loc.fill(value)
                return

    _fill_if_visible(['input[placeholder="MM"]', 'input[name="month"]'], str(dt.month).zfill(2))
    _fill_if_visible(['input[placeholder="DD"]', 'input[name="day"]'], str(dt.day).zfill(2))
    _fill_if_visible(['input[placeholder="YYYY"]', 'input[name="year"]'], str(dt.year))
    _fill_if_visible(['input[placeholder="HH"]', 'input[name="hour"]'], str(dt.hour).zfill(2))
    _fill_if_visible(['input[placeholder="MM"]', 'input[name="minute"]'], "00")

    # Confirm scheduling
    confirm_btn = page.get_by_role(
        "button", name=re.compile(r"schedule|confirm|done", re.I)
    ).last
    if confirm_btn.count() > 0:
        confirm_btn.click()
        page.wait_for_timeout(2000)


def _save_draft(page) -> None:
    """Save the post as a draft (no scheduling)."""
    save_btn = page.get_by_role("button", name=re.compile(r"^save$", re.I)).first
    if save_btn.count() > 0 and save_btn.is_visible():
        save_btn.click()
    page.wait_for_timeout(1500)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _screenshot(page, name: str) -> None:
    """Save a full-page screenshot to logs/ for post-mortem debugging."""
    try:
        path = f"logs/{name}.png"
        page.screenshot(path=path, full_page=True)
        logger.info(f"Debug screenshot saved: {path}")
    except Exception:
        pass  # Never let screenshot failure mask the real error
