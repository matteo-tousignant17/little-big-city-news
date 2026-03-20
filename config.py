"""
config.py - Central configuration loader for What's Up [CITY] newsletter system.
Loads environment variables, city config, and sponsor definitions.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent


# ─── API Keys ────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
BEEHIIV_API_KEY: str = os.environ.get("BEEHIIV_API_KEY", "")
FIRECRAWL_API_KEY: str = os.environ.get("FIRECRAWL_API_KEY", "")

CITY_SLUG: str = os.environ.get("CITY_SLUG", "boise")

# human-in-loop: "none" | "local" | "email"
HUMAN_APPROVAL: str = os.environ.get("HUMAN_APPROVAL", "none")

# Email config (only needed if HUMAN_APPROVAL == "email")
APPROVAL_EMAIL_TO: str = os.environ.get("APPROVAL_EMAIL_TO", "")
APPROVAL_EMAIL_FROM: str = os.environ.get("APPROVAL_EMAIL_FROM", "")
SMTP_HOST: str = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT: int = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER: str = os.environ.get("SMTP_USER", "")
SMTP_PASS: str = os.environ.get("SMTP_PASS", "")


# ─── Data Models ─────────────────────────────────────────────────────────────

@dataclass
class EventSource:
    name: str
    url: str
    type: str  # eventbrite | city_calendar | news_events | alt_weekly | tourism | venue


@dataclass
class RealEstateConfig:
    zillow_search_url: str
    market_area: str
    featured_neighborhoods: list[str]


@dataclass
class CityConfig:
    city: str
    state: str
    state_abbr: str
    slug: str
    newsletter_name: str
    tagline: str
    greeting: str
    timezone: str
    beehiiv_publication_id: str
    send_day: str
    send_hour: int
    event_sources: list[EventSource]
    real_estate: RealEstateConfig
    social: dict


@dataclass
class Sponsor:
    name: str
    tagline: str
    url: str
    tier: str          # gold | silver | bronze
    active: bool
    image_url: str = ""
    promo_code: str = ""
    cta_text: str = "Learn More"
    category: str = ""  # real_estate | restaurant | retail | service | event


@dataclass
class Event:
    title: str
    description: str
    date: str          # ISO date string YYYY-MM-DD
    day_name: str      # Thursday | Friday | Saturday | Sunday
    start_time: str    # e.g. "7:00 PM"
    end_time: str      # e.g. "10:00 PM" or ""
    location: str
    address: str
    cost: str          # "Free" | "$15" | "$10-25"
    url: str
    category: str      # music | food | family | arts | sports | community | outdoor
    family_friendly: bool = True
    source: str = ""


@dataclass
class NewsletterContext:
    city_config: CityConfig
    sponsors: list[Sponsor]
    events: list[Event]
    trivia_question: str = ""
    trivia_answer: str = ""
    intro_text: str = ""
    featured_home: dict = field(default_factory=dict)
    real_estate_spotlight: dict = field(default_factory=dict)
    publish_date: str = ""
    week_range: str = ""


# ─── Loaders ─────────────────────────────────────────────────────────────────

def load_city_config(slug: Optional[str] = None) -> CityConfig:
    """Load city configuration from cities/<slug>/config.json."""
    slug = slug or CITY_SLUG
    config_path = BASE_DIR / "cities" / slug / "config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"City config not found: {config_path}")

    with open(config_path) as f:
        data = json.load(f)

    sources = [EventSource(**s) for s in data.get("event_sources", [])]
    re_cfg = RealEstateConfig(**data.get("real_estate", {}))

    return CityConfig(
        city=data["city"],
        state=data["state"],
        state_abbr=data["state_abbr"],
        slug=data["slug"],
        newsletter_name=data["newsletter_name"],
        tagline=data["tagline"],
        greeting=data["greeting"],
        timezone=data["timezone"],
        beehiiv_publication_id=data["beehiiv_publication_id"],
        send_day=data.get("send_day", "thursday"),
        send_hour=data.get("send_hour", 7),
        event_sources=sources,
        real_estate=re_cfg,
        social=data.get("social", {}),
    )


def load_sponsors(slug: Optional[str] = None) -> list[Sponsor]:
    """Load active sponsors from cities/<slug>/sponsors.json, falling back to root sponsors.json."""
    slug = slug or CITY_SLUG
    city_sponsors = BASE_DIR / "cities" / slug / "sponsors.json"
    root_sponsors = BASE_DIR / "sponsors.json"

    sponsors_path = city_sponsors if city_sponsors.exists() else root_sponsors
    if not sponsors_path.exists():
        return []

    with open(sponsors_path) as f:
        data = json.load(f)

    return [Sponsor(**s) for s in data.get("sponsors", []) if s.get("active", True)]


def validate_keys() -> list[str]:
    """Return list of missing required API keys."""
    missing = []
    if not ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")
    if not FIRECRAWL_API_KEY:
        missing.append("FIRECRAWL_API_KEY")
    # beehiiv auth is checked at publish time (BEEHIIV_AUTH_STATE env var or auth_state.json)
    return missing
