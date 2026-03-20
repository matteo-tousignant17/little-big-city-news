"""
scrape_events.py — Parallel event scraping via Firecrawl for What's Up [CITY].

Strategy:
- Scrape 6+ sources concurrently using asyncio
- Extract raw event data into structured Event objects
- Filter ruthlessly: positive, family-friendly, local, upcoming Thu-Sun
- Use Claude Sonnet 4.6 to parse unstructured scraped text into Event objects
"""

import asyncio
import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import anthropic
from firecrawl import FirecrawlApp

from config import (
    ANTHROPIC_API_KEY,
    FIRECRAWL_API_KEY,
    CityConfig,
    Event,
    EventSource,
    load_city_config,
)

logger = logging.getLogger(__name__)


# ─── Date Helpers ─────────────────────────────────────────────────────────────

def get_weekend_dates(city_tz: str = "America/Boise") -> dict[str, str]:
    """Return the upcoming Thu–Sun dates in YYYY-MM-DD format."""
    tz = ZoneInfo(city_tz)
    today = datetime.now(tz).date()

    # Find next Thursday (weekday 3)
    days_until_thu = (3 - today.weekday()) % 7
    if days_until_thu == 0:
        days_until_thu = 7  # already Thursday → next week's
    thursday = today + timedelta(days=days_until_thu)

    return {
        "thursday": thursday.isoformat(),
        "friday": (thursday + timedelta(1)).isoformat(),
        "saturday": (thursday + timedelta(2)).isoformat(),
        "sunday": (thursday + timedelta(3)).isoformat(),
    }


# ─── Firecrawl Scraper ────────────────────────────────────────────────────────

class EventScraper:
    def __init__(self):
        self.firecrawl = FirecrawlApp(api_key=FIRECRAWL_API_KEY)
        self.claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    def scrape_url(self, url: str, source_name: str) -> str:
        """Scrape a single URL and return clean markdown text."""
        try:
            result = self.firecrawl.scrape(
                url=url,
                formats=["markdown"],
                actions=[{"type": "wait", "milliseconds": 2000}],
            )
            markdown = result.get("markdown", "") or ""
            logger.info(f"Scraped {source_name}: {len(markdown)} chars")
            return markdown[:15000]  # cap at 15k chars per source
        except Exception as e:
            logger.warning(f"Failed to scrape {source_name} ({url}): {e}")
            return ""

    async def scrape_url_async(self, source: EventSource) -> tuple[str, str]:
        """Async wrapper for scraping a single source."""
        loop = asyncio.get_event_loop()
        markdown = await loop.run_in_executor(None, self.scrape_url, source.url, source.name)
        return source.name, markdown

    async def scrape_all_sources(self, city_config: CityConfig) -> dict[str, str]:
        """Scrape all city event sources in parallel. Returns {source_name: markdown}."""
        tasks = [self.scrape_url_async(src) for src in city_config.event_sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        scraped = {}
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"Scrape task failed: {result}")
                continue
            name, markdown = result
            if markdown:
                scraped[name] = markdown

        logger.info(f"Successfully scraped {len(scraped)}/{len(city_config.event_sources)} sources")
        return scraped

    def parse_events_with_claude(
        self,
        scraped_content: dict[str, str],
        weekend_dates: dict[str, str],
        city_config: CityConfig,
    ) -> list[Event]:
        """Use Claude Sonnet 4.6 to extract structured events from scraped markdown."""

        # Build combined content string
        content_blocks = []
        for source_name, markdown in scraped_content.items():
            content_blocks.append(f"=== SOURCE: {source_name} ===\n{markdown}\n")
        combined = "\n".join(content_blocks)

        thu = weekend_dates["thursday"]
        fri = weekend_dates["friday"]
        sat = weekend_dates["saturday"]
        sun = weekend_dates["sunday"]

        prompt = f"""You are extracting local events for a community newsletter for {city_config.city}, {city_config.state}.

Weekend dates we want events for:
- Thursday: {thu}
- Friday: {fri}
- Saturday: {sat}
- Sunday: {sun}

SCRAPED EVENT SOURCES:
{combined}

Extract ALL events happening on Thursday {thu} through Sunday {sun} in {city_config.city}.

STRICT FILTERS — EXCLUDE anything that is:
- Crime, violence, arrests, protests, political rallies
- Adult-only events (18+, 21+ unless it's a restaurant/bar with food focus)
- Controversial or divisive topics
- Events outside the {city_config.city} metro area
- Events with no clear date/time

INCLUDE events that are:
- Family-friendly festivals, concerts, markets, classes, sports, art shows
- Restaurant openings, food events, wine/beer tastings (if family welcome)
- Community gatherings, outdoor activities, holiday events
- Free OR ticketed events (both are fine)
- Unique, interesting, or "only in {city_config.city}" type events

For each event, return a JSON array. Each event object must have:
{{
  "title": "Event name",
  "description": "1-2 sentence description, upbeat and enticing",
  "date": "YYYY-MM-DD",
  "day_name": "Thursday|Friday|Saturday|Sunday",
  "start_time": "7:00 PM",
  "end_time": "10:00 PM or empty string",
  "location": "Venue name",
  "address": "Street address or neighborhood",
  "cost": "Free | $15 | $10-25",
  "url": "https://... or empty string",
  "category": "music|food|family|arts|sports|community|outdoor",
  "family_friendly": true,
  "source": "source name"
}}

Return ONLY valid JSON array. No markdown, no explanation. If no events found, return [].
Aim for 8-15 high-quality events spread across Thu-Sun. Quality over quantity."""

        response = self.claude.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()

        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

        try:
            events_data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude event JSON: {e}\nRaw: {raw[:500]}")
            return []

        events = []
        for item in events_data:
            try:
                events.append(Event(
                    title=item.get("title", ""),
                    description=item.get("description", ""),
                    date=item.get("date", ""),
                    day_name=item.get("day_name", ""),
                    start_time=item.get("start_time", ""),
                    end_time=item.get("end_time", ""),
                    location=item.get("location", ""),
                    address=item.get("address", ""),
                    cost=item.get("cost", ""),
                    url=item.get("url", ""),
                    category=item.get("category", "community"),
                    family_friendly=item.get("family_friendly", True),
                    source=item.get("source", ""),
                ))
            except Exception as e:
                logger.warning(f"Skipping malformed event: {e}")

        logger.info(f"Extracted {len(events)} events after filtering")
        return events

    def quality_check(self, events: list[Event]) -> list[Event]:
        """Final quality pass — deduplicate and ensure minimum data quality."""
        seen_titles = set()
        clean = []
        for ev in events:
            normalized = ev.title.lower().strip()
            if not normalized or normalized in seen_titles:
                continue
            if not ev.date or not ev.location:
                continue
            seen_titles.add(normalized)
            clean.append(ev)
        return clean

    def group_by_day(self, events: list[Event]) -> dict[str, list[Event]]:
        """Group events by day name."""
        groups: dict[str, list[Event]] = {
            "Thursday": [],
            "Friday": [],
            "Saturday": [],
            "Sunday": [],
        }
        for ev in events:
            day = ev.day_name.capitalize()
            if day in groups:
                groups[day].append(ev)
        return groups


# ─── Public API ───────────────────────────────────────────────────────────────

async def scrape_events(city_config: Optional[CityConfig] = None) -> tuple[list[Event], dict[str, str]]:
    """
    Main entry point: scrape all sources and return (events_list, weekend_dates).
    Call from main.py or run standalone for testing.
    """
    if city_config is None:
        city_config = load_city_config()

    weekend_dates = get_weekend_dates(city_config.timezone)
    logger.info(f"Scraping events for {city_config.city} | Weekend: {weekend_dates['thursday']} – {weekend_dates['sunday']}")

    scraper = EventScraper()
    scraped = await scraper.scrape_all_sources(city_config)

    if not scraped:
        logger.error("No sources scraped successfully. Using empty event list.")
        return [], weekend_dates

    events = scraper.parse_events_with_claude(scraped, weekend_dates, city_config)
    events = scraper.quality_check(events)
    return events, weekend_dates


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    async def main():
        events, dates = await scrape_events()
        print(f"\nFound {len(events)} events for {dates['thursday']} – {dates['sunday']}")
        for ev in events:
            print(f"  [{ev.day_name}] {ev.title} @ {ev.location} | {ev.cost}")

    asyncio.run(main())
