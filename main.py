"""
main.py — Weekly orchestration for What's Up [CITY] newsletter.

Uses Claude Opus 4.6 as orchestrator with parallel sub-tasks:
  1. [parallel] Scrape events + Generate content
  2. Build newsletter HTML
  3. Quality check
  4. Send/schedule via beehiiv

Run manually:   python main.py
Run for a city: python main.py --city boise
Dry run:        python main.py --dry-run
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import anthropic

from build_newsletter import build_newsletter_html, build_subject_line, save_draft
from config import (
    ANTHROPIC_API_KEY,
    CITY_SLUG,
    NewsletterContext,
    load_city_config,
    load_sponsors,
    validate_keys,
)
from generate_content import generate_all_content
from scrape_events import scrape_events
from send_newsletter import send_newsletter

# ─── Logging setup ───────────────────────────────────────────────────────────
log_dir = Path(__file__).parent / "logs"
log_dir.mkdir(exist_ok=True)

log_file = log_dir / f"newsletter_{date.today().isoformat()}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("main")

# ─── Orchestrator Claude client ───────────────────────────────────────────────
opus_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ─── Parallel Orchestration ───────────────────────────────────────────────────

async def run_parallel_tasks(city_config, publish_date: str, week_range: str):
    """
    Run event scraping and content generation concurrently.
    Returns (events, content_dict).
    """
    loop = asyncio.get_event_loop()

    async def run_scraper():
        logger.info("Sub-agent: Starting event scraper...")
        events, weekend_dates = await scrape_events(city_config)
        logger.info(f"Sub-agent: Scraped {len(events)} events")
        return events, weekend_dates

    async def run_content_gen(events_placeholder: list):
        """Start content generation — uses events if available, empty list otherwise."""
        logger.info("Sub-agent: Starting content generator...")
        content = await loop.run_in_executor(
            None,
            generate_all_content,
            city_config,
            events_placeholder,
            publish_date,
            week_range,
        )
        logger.info("Sub-agent: Content generation complete")
        return content

    # Run scraper first (we need event count for intro), then content gen with real events
    # For speed: start content gen with empty events list, we'll update intro if needed
    scraper_task = asyncio.create_task(run_scraper())
    content_task = asyncio.create_task(run_content_gen([]))

    events_result, weekend_dates = await scraper_task
    content_result = await content_task

    # If we have events, optionally regenerate intro with actual event data for better teaser
    if events_result and len(events_result) > 3:
        logger.info("Regenerating intro with real event data...")
        content_result = await loop.run_in_executor(
            None,
            generate_all_content,
            city_config,
            events_result,
            publish_date,
            week_range,
        )

    return events_result, content_result


# ─── Quality Checks ───────────────────────────────────────────────────────────

def quality_check(html: str, ctx: NewsletterContext) -> tuple[bool, list[str]]:
    """Basic quality checks before sending. Returns (passed, issues)."""
    issues = []

    if len(html) < 2000:
        issues.append("HTML is suspiciously short (< 2000 chars)")

    if not ctx.events:
        issues.append("WARNING: No events found — newsletter may feel thin")

    if not ctx.intro_text:
        issues.append("Missing intro text")

    if not ctx.trivia_question:
        issues.append("Missing trivia question")

    if ctx.city_config.beehiiv_publication_id == "YOUR_BEEHIIV_PUBLICATION_ID":
        issues.append("ERROR: beehiiv publication_id not configured")

    critical = [i for i in issues if i.startswith("ERROR")]
    if critical:
        return False, issues

    return True, issues


# ─── Orchestrator Summary ─────────────────────────────────────────────────────

def log_orchestrator_summary(ctx: NewsletterContext, result: dict):
    """Use Claude Opus to write a concise run summary log."""
    event_count = len(ctx.events)
    sponsor_count = len([s for s in ctx.sponsors if s.active])
    status = result.get("status", "unknown")

    summary_prompt = f"""Write a 3-bullet summary of this newsletter run for the operator log.

Newsletter: {ctx.city_config.newsletter_name}
Date: {ctx.publish_date}
Events found: {event_count} (Thu-Sun)
Active sponsors: {sponsor_count}
Status: {status}
Subject line: {result.get('subject', 'N/A')}

Be factual, brief. Note anything worth the operator's attention. No fluff."""

    try:
        response = opus_client.messages.create(
            model="claude-opus-4-6",
            max_tokens=200,
            messages=[{"role": "user", "content": summary_prompt}],
        )
        summary = response.content[0].text.strip()
        logger.info(f"\n{'='*50}\nORCHESTRATOR SUMMARY\n{summary}\n{'='*50}")
    except Exception as e:
        logger.warning(f"Could not generate orchestrator summary: {e}")


# ─── Main Entry Point ─────────────────────────────────────────────────────────

async def run(city_slug: Optional[str] = None, dry_run: bool = False):
    """Full weekly newsletter run."""
    logger.info("=" * 60)
    logger.info("What's Up [CITY] Newsletter System — Starting run")
    logger.info("=" * 60)

    # 0. Validate config
    missing_keys = validate_keys()
    if missing_keys:
        logger.error(f"Missing API keys: {', '.join(missing_keys)}")
        logger.error("Copy .env.example to .env and fill in your keys.")
        if not dry_run:
            sys.exit(1)

    # 1. Load config
    city_config = load_city_config(city_slug)
    sponsors = load_sponsors(city_slug)
    tz = ZoneInfo(city_config.timezone)
    now = datetime.now(tz)

    logger.info(f"City: {city_config.city}, {city_config.state}")
    logger.info(f"Sponsors loaded: {len(sponsors)} active")

    # Build date strings
    publish_date = now.strftime("%B %d, %Y")
    from scrape_events import get_weekend_dates
    weekend_dates = get_weekend_dates(city_config.timezone)
    thu = datetime.fromisoformat(weekend_dates["thursday"]).strftime("%b %d")
    sun = datetime.fromisoformat(weekend_dates["sunday"]).strftime("%b %d")
    week_range = f"{thu}–{sun}"

    logger.info(f"Weekend: {week_range}")

    # 2. Run parallel tasks (scraping + content gen)
    logger.info("Starting parallel sub-agents: scraper + content generator...")
    events, content = await run_parallel_tasks(city_config, publish_date, week_range)

    # 3. Build context
    ctx = NewsletterContext(
        city_config=city_config,
        sponsors=sponsors,
        events=events,
        trivia_question=content.get("trivia_question", ""),
        trivia_answer=content.get("trivia_answer", ""),
        intro_text=content.get("intro", ""),
        featured_home=content.get("featured_home", {}),
        real_estate_spotlight=content.get("real_estate_spotlight", {}),
        publish_date=publish_date,
        week_range=week_range,
    )

    # 4. Build HTML
    logger.info("Building newsletter HTML...")
    html = build_newsletter_html(ctx)
    subject = build_subject_line(ctx)
    logger.info(f"Subject: {subject}")
    logger.info(f"HTML length: {len(html):,} chars")

    # 5. Save draft
    draft_path = save_draft(html, ctx)

    # 6. Quality check
    passed, issues = quality_check(html, ctx)
    for issue in issues:
        if issue.startswith("ERROR"):
            logger.error(issue)
        elif issue.startswith("WARNING"):
            logger.warning(issue)
        else:
            logger.info(f"Quality note: {issue}")

    if not passed:
        logger.error("Quality check FAILED. Newsletter not sent.")
        logger.error(f"Fix the errors above, then run: python send_newsletter.py --publish POST_ID")
        sys.exit(1)

    # 7. Send/schedule
    if dry_run:
        logger.info("DRY RUN mode — skipping beehiiv send. Draft saved to disk only.")
        result = {"status": "dry_run", "subject": subject, "draft_path": str(draft_path)}
    else:
        logger.info("Sending to beehiiv...")
        result = send_newsletter(ctx, html, subject, draft_path)

    # 8. Log orchestrator summary
    log_orchestrator_summary(ctx, result)

    logger.info("Run complete!")
    logger.info(json.dumps(result, indent=2, default=str))
    return result


def main():
    parser = argparse.ArgumentParser(description="What's Up [CITY] Newsletter — Weekly Run")
    parser.add_argument("--city", default=None, help="City slug (e.g. boise)")
    parser.add_argument("--dry-run", action="store_true", help="Build newsletter but don't send to beehiiv")
    args = parser.parse_args()

    asyncio.run(run(city_slug=args.city, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
