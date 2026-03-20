"""
send_newsletter.py — beehiiv API integration for What's Up [CITY].

Handles:
- Creating a draft post via beehiiv API
- Scheduling the post for Thursday morning delivery
- Human-in-loop approval (local draft save or email)
- Sending email approval previews
"""

import json
import logging
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import requests

from config import (
    BEEHIIV_API_KEY,
    HUMAN_APPROVAL,
    APPROVAL_EMAIL_TO,
    APPROVAL_EMAIL_FROM,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASS,
    CityConfig,
    NewsletterContext,
)

logger = logging.getLogger(__name__)

BEEHIIV_API_BASE = "https://api.beehiiv.com/v2"


# ─── beehiiv API ─────────────────────────────────────────────────────────────

def get_scheduled_send_time(city_config: CityConfig) -> str:
    """
    Return ISO 8601 timestamp for the next Thursday at send_hour in city timezone.
    beehiiv expects UTC timestamp in ISO format.
    """
    tz = ZoneInfo(city_config.timezone)
    now = datetime.now(tz)

    # Find next Thursday
    days_until_thu = (3 - now.weekday()) % 7
    if days_until_thu == 0:
        days_until_thu = 7  # skip today if already Thursday
    send_local = now.replace(
        hour=city_config.send_hour,
        minute=0,
        second=0,
        microsecond=0,
    ) + timedelta(days=days_until_thu)

    # Convert to UTC for API
    send_utc = send_local.astimezone(ZoneInfo("UTC"))
    return send_utc.isoformat()


def create_beehiiv_post(
    ctx: NewsletterContext,
    html_content: str,
    subject_line: str,
    scheduled: bool = True,
) -> dict:
    """
    Create a post in beehiiv via API.
    Returns the API response dict.

    Docs: https://developers.beehiiv.com/api-reference/posts/create
    """
    publication_id = ctx.city_config.beehiiv_publication_id
    if not publication_id or publication_id == "YOUR_BEEHIIV_PUBLICATION_ID":
        raise ValueError("beehiiv publication_id not configured. Set it in cities/<slug>/config.json")

    headers = {
        "Authorization": f"Bearer {BEEHIIV_API_KEY}",
        "Content-Type": "application/json",
    }

    payload: dict = {
        "title": subject_line,
        "subject": subject_line,
        "preview_text": f"Your weekly guide to the best of {ctx.city_config.city} 🎉",
        "body_html": html_content,
        "status": "draft",  # always create as draft first
        "platform": "email",
        "audience": "free",
    }

    if scheduled:
        scheduled_at = get_scheduled_send_time(ctx.city_config)
        payload["scheduled_at"] = scheduled_at
        logger.info(f"Scheduling beehiiv post for {scheduled_at}")
    else:
        payload["status"] = "draft"

    url = f"{BEEHIIV_API_BASE}/publications/{publication_id}/posts"

    logger.info(f"Creating beehiiv post: {subject_line}")
    response = requests.post(url, headers=headers, json=payload, timeout=30)

    if response.status_code not in (200, 201):
        logger.error(f"beehiiv API error {response.status_code}: {response.text}")
        response.raise_for_status()

    data = response.json()
    post_id = data.get("data", {}).get("id", "")
    logger.info(f"beehiiv post created: id={post_id}")
    return data


def publish_beehiiv_post(publication_id: str, post_id: str) -> dict:
    """Publish (or confirm scheduling of) an existing draft post."""
    headers = {
        "Authorization": f"Bearer {BEEHIIV_API_KEY}",
        "Content-Type": "application/json",
    }
    url = f"{BEEHIIV_API_BASE}/publications/{publication_id}/posts/{post_id}"
    response = requests.patch(
        url,
        headers=headers,
        json={"status": "confirmed"},
        timeout=30,
    )
    if response.status_code not in (200, 201):
        logger.error(f"beehiiv publish error {response.status_code}: {response.text}")
        response.raise_for_status()
    return response.json()


# ─── Human-in-Loop ────────────────────────────────────────────────────────────

def send_approval_email(html_content: str, subject: str, ctx: NewsletterContext) -> bool:
    """Send the draft newsletter to the operator for approval via SMTP. Returns True on success."""
    if not all([APPROVAL_EMAIL_TO, SMTP_USER, SMTP_PASS]):
        logger.warning("Email approval config incomplete. Falling back to local draft.")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[APPROVAL NEEDED] {ctx.city_config.newsletter_name} — {subject}"
        msg["From"] = APPROVAL_EMAIL_FROM or SMTP_USER
        msg["To"] = APPROVAL_EMAIL_TO

        text_part = MIMEText(
            f"Your newsletter draft is ready for review!\n\nSubject: {subject}\n\n"
            "This HTML email preview is attached. Reply to approve, or edit the draft in beehiiv.",
            "plain",
        )
        html_part = MIMEText(html_content, "html")

        msg.attach(text_part)
        msg.attach(html_part)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(msg["From"], [APPROVAL_EMAIL_TO], msg.as_string())

        logger.info(f"Approval email sent to {APPROVAL_EMAIL_TO}")
        return True
    except Exception as e:
        logger.error(f"Failed to send approval email: {e}")
        return False


# ─── Main Send Flow ───────────────────────────────────────────────────────────

def send_newsletter(
    ctx: NewsletterContext,
    html_content: str,
    subject_line: str,
    draft_path: Optional[Path] = None,
) -> dict:
    """
    Full send flow:
    1. If HUMAN_APPROVAL == "email" → send preview email, create beehiiv draft
    2. If HUMAN_APPROVAL == "local" → save draft, create beehiiv draft (don't schedule)
    3. If HUMAN_APPROVAL == "none" → create beehiiv draft + schedule immediately

    Returns result dict with status and beehiiv response.
    """
    result = {
        "status": "unknown",
        "subject": subject_line,
        "city": ctx.city_config.city,
        "beehiiv_response": None,
        "draft_path": str(draft_path) if draft_path else None,
    }

    approval_mode = HUMAN_APPROVAL.lower()

    if approval_mode == "email":
        logger.info("Human approval mode: email — sending preview...")
        email_sent = send_approval_email(html_content, subject_line, ctx)
        if not email_sent:
            logger.warning("Email send failed — saving draft locally instead")

        # Create beehiiv draft (no schedule)
        try:
            api_response = create_beehiiv_post(ctx, html_content, subject_line, scheduled=False)
            result["beehiiv_response"] = api_response
            result["status"] = "draft_pending_approval"
            logger.info("beehiiv draft created. Review and schedule manually in beehiiv dashboard.")
        except Exception as e:
            logger.error(f"beehiiv draft creation failed: {e}")
            result["status"] = "error"
            result["error"] = str(e)

    elif approval_mode == "local":
        logger.info("Human approval mode: local — draft saved, beehiiv draft created...")
        try:
            api_response = create_beehiiv_post(ctx, html_content, subject_line, scheduled=False)
            result["beehiiv_response"] = api_response
            result["status"] = "draft_pending_local_approval"
            logger.info(f"Draft saved to {draft_path}. Run: python send_newsletter.py --publish POST_ID to schedule.")
        except Exception as e:
            logger.error(f"beehiiv draft creation failed: {e}")
            result["status"] = "error"
            result["error"] = str(e)

    else:  # "none" = fully autopilot
        logger.info("Autopilot mode: creating and scheduling beehiiv post...")
        try:
            api_response = create_beehiiv_post(ctx, html_content, subject_line, scheduled=True)
            result["beehiiv_response"] = api_response
            result["status"] = "scheduled"
            scheduled_at = get_scheduled_send_time(ctx.city_config)
            logger.info(f"Newsletter scheduled for {scheduled_at}")
        except Exception as e:
            logger.error(f"beehiiv scheduling failed: {e}")
            result["status"] = "error"
            result["error"] = str(e)

    return result


if __name__ == "__main__":
    import sys
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Send newsletter or publish a draft")
    parser.add_argument("--publish", metavar="POST_ID", help="Publish an existing beehiiv draft post by ID")
    parser.add_argument("--city", default=None, help="City slug to use")
    args = parser.parse_args()

    if args.publish:
        from config import load_city_config
        city_config = load_city_config(args.city)
        pub_id = city_config.beehiiv_publication_id
        result = publish_beehiiv_post(pub_id, args.publish)
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python send_newsletter.py --publish POST_ID")
        print("       (Full send flow is run via main.py)")
