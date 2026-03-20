"""
generate_content.py — Claude Sonnet 4.6 content generator for What's Up [CITY].

Generates:
- Positive, punchy newsletter intro + hook
- Fresh local trivia question + answer (Boise/city-specific)
- Real estate market spotlight copy
- Featured home "guess the price" block (Zillow scrape or placeholder)
"""

import json
import logging
import re
from datetime import date
from typing import Optional

import anthropic
from firecrawl import FirecrawlApp

from config import (
    ANTHROPIC_API_KEY,
    FIRECRAWL_API_KEY,
    CityConfig,
    Event,
    Sponsor,
    load_city_config,
)

logger = logging.getLogger(__name__)

claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ─── Intro + Hook ─────────────────────────────────────────────────────────────

def generate_intro(
    city_config: CityConfig,
    events: list[Event],
    publish_date: str,
    week_range: str,
) -> str:
    """Generate a warm, upbeat newsletter intro paragraph."""
    event_teaser = ", ".join([e.title for e in events[:4]]) if events else "tons of great events"

    prompt = f"""You write the intro for "{city_config.newsletter_name}", a beloved weekly local newsletter for {city_config.city}, {city_config.state}.

Newsletter date: {publish_date}
Weekend covered: {week_range}
Top events this issue: {event_teaser}

Write a SHORT, warm, conversational intro (3-5 sentences max). Rules:
- Start with "{city_config.greeting}"
- Sound like a friendly local neighbor, NOT a corporate bot
- Reference ONE specific thing about the weekend or season that feels current/authentic
- Tease the best event or vibe of the weekend
- End with a transition like "Here's what's happening 👇" or "Let's get into it 👇"
- No politics, no crime, no negativity — pure positive local energy
- Use 1-2 emojis max, naturally placed
- Keep it under 80 words

Return ONLY the intro text, no labels or formatting."""

    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


# ─── Trivia ───────────────────────────────────────────────────────────────────

def generate_trivia(city_config: CityConfig) -> tuple[str, str]:
    """Generate a fresh local trivia question + answer about the city."""
    prompt = f"""Generate a fun, surprising local trivia question about {city_config.city}, {city_config.state}.

Rules:
- The fact should be something most locals don't know
- Could be about history, geography, food, famous people, unique records, nature, pop culture connection
- Must be 100% factual and verifiable
- Should make someone say "Whoa, I didn't know that!"
- Family-friendly, positive, interesting

Return ONLY a JSON object with two fields:
{{"question": "The trivia question here?", "answer": "The full answer with a brief interesting detail."}}

No markdown, no explanation. Just the JSON."""

    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    try:
        data = json.loads(raw)
        return data.get("question", ""), data.get("answer", "")
    except json.JSONDecodeError:
        logger.warning("Trivia JSON parse failed, using fallback")
        return (
            f"What is the nickname of {city_config.city}?",
            f"{city_config.city} is known for its vibrant culture and great community!"
        )


# ─── Real Estate Spotlight ────────────────────────────────────────────────────

def generate_real_estate_spotlight(city_config: CityConfig) -> dict:
    """Generate real estate market copy + optional featured neighborhood spotlight."""
    neighborhood = city_config.real_estate.featured_neighborhoods[
        date.today().isocalendar().week % len(city_config.real_estate.featured_neighborhoods)
    ]

    prompt = f"""Write a short, engaging real estate spotlight for a local newsletter about {city_config.city}, {city_config.state}.

Featured neighborhood this week: {neighborhood}
Market area: {city_config.real_estate.market_area}
Current date: {date.today().isoformat()}

Write TWO sections (return as JSON):
1. "market_blurb": 2-3 sentences on the current {city_config.city} real estate vibe. Keep it positive, informative, actionable. No fake numbers — if you don't know current stats, speak generally about the market character.
2. "neighborhood_spotlight": 3-4 sentences spotlighting {neighborhood}. Why do people love living there? What's walkable, special, distinctive? Make people want to live there.

Return ONLY valid JSON:
{{"market_blurb": "...", "neighborhood_spotlight": "...", "neighborhood": "{neighborhood}"}}"""

    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Real estate JSON parse failed, using fallback")
        return {
            "market_blurb": f"The {city_config.city} real estate market continues to be one of the most dynamic in the region. Whether you're buying, selling, or just curious, it's a great time to connect with a local agent.",
            "neighborhood_spotlight": f"{neighborhood} is one of {city_config.city}'s most beloved neighborhoods — great walkability, friendly neighbors, and a character all its own.",
            "neighborhood": neighborhood,
        }


# ─── Featured Home (Zillow Scrape) ────────────────────────────────────────────

def fetch_featured_home(city_config: CityConfig) -> dict:
    """
    Attempt to scrape a featured listing from Zillow.
    Returns a dict with listing details, or a placeholder if scrape fails.
    """
    placeholder = {
        "address": f"A beautiful home in {city_config.city}",
        "price": "???",
        "beds": 3,
        "baths": 2,
        "sqft": "",
        "image_url": "",
        "zillow_url": city_config.real_estate.zillow_search_url,
        "description": f"What would you guess this {city_config.city} home is listed for? Click to see the answer!",
        "is_placeholder": True,
    }

    if not FIRECRAWL_API_KEY:
        return placeholder

    try:
        fc = FirecrawlApp(api_key=FIRECRAWL_API_KEY)
        result = fc.scrape_url(
            city_config.real_estate.zillow_search_url,
            formats=["markdown"],
        )
        markdown = result.get("markdown", "")[:8000]

        if not markdown:
            return placeholder

        prompt = f"""From this Zillow search results page for {city_config.city}, extract the FIRST featured listing.

PAGE CONTENT:
{markdown}

Return ONLY JSON with these fields (use empty string if not found):
{{
  "address": "street address",
  "price": "$XXX,XXX",
  "beds": 3,
  "baths": 2,
  "sqft": "1,800 sqft",
  "zillow_url": "https://zillow.com/...",
  "description": "One sentence about the home's appeal"
}}"""

        response = claude.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

        data = json.loads(raw)
        data["is_placeholder"] = False
        data.setdefault("image_url", "")
        return data

    except Exception as e:
        logger.warning(f"Featured home scrape failed: {e}")
        return placeholder


# ─── Public API ───────────────────────────────────────────────────────────────

def generate_all_content(
    city_config: Optional[CityConfig] = None,
    events: Optional[list[Event]] = None,
    publish_date: str = "",
    week_range: str = "",
) -> dict:
    """
    Generate all newsletter content sections.
    Returns a dict with: intro, trivia_question, trivia_answer,
    featured_home, real_estate_spotlight.
    """
    if city_config is None:
        city_config = load_city_config()

    events = events or []

    logger.info("Generating newsletter intro...")
    intro = generate_intro(city_config, events, publish_date, week_range)

    logger.info("Generating trivia...")
    trivia_q, trivia_a = generate_trivia(city_config)

    logger.info("Generating real estate spotlight...")
    re_spotlight = generate_real_estate_spotlight(city_config)

    logger.info("Fetching featured home...")
    featured_home = fetch_featured_home(city_config)

    return {
        "intro": intro,
        "trivia_question": trivia_q,
        "trivia_answer": trivia_a,
        "real_estate_spotlight": re_spotlight,
        "featured_home": featured_home,
    }


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    content = generate_all_content()
    print("\n=== GENERATED CONTENT ===")
    print(f"INTRO:\n{content['intro']}\n")
    print(f"TRIVIA Q: {content['trivia_question']}")
    print(f"TRIVIA A: {content['trivia_answer']}\n")
    print(f"RE SPOTLIGHT: {content['real_estate_spotlight']['market_blurb']}\n")
    print(f"FEATURED HOME: {content['featured_home']['address']} — {content['featured_home']['price']}")
