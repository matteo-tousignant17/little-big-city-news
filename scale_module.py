"""
scale_module.py — One-command city cloning for What's Up [CITY] empire.

Usage:
  python scale_module.py --city "Portland" --state "Oregon" --state-abbr "OR" --timezone "America/Los_Angeles"
  python scale_module.py --list     # show all configured cities
  python scale_module.py --status   # show revenue/sub stats placeholder per city

What it does:
  1. Creates cities/<slug>/config.json with city-specific event sources
  2. Creates cities/<slug>/sponsors.json with placeholder sponsors
  3. Uses Claude to auto-discover the best local event sources for the city
  4. Outputs a checklist of next steps for the new city

Revenue extensions (--extension flag):
  --extension merch         # Add Printful/Printify merch hooks to config
  --extension events        # Add local event hosting revenue module
  --extension premium       # Add beehiiv premium subscription tier config
  --extension coupon-book   # Add seasonal coupon book revenue config
  --extension dashboard     # Generate holding company multi-city dashboard
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Optional

import anthropic

from config import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

BASE_DIR = Path(__file__).parent
CITIES_DIR = BASE_DIR / "cities"

claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ─── Timezone defaults ────────────────────────────────────────────────────────

TIMEZONE_DEFAULTS = {
    "AK": "America/Anchorage",
    "AL": "America/Chicago",
    "AR": "America/Chicago",
    "AZ": "America/Phoenix",
    "CA": "America/Los_Angeles",
    "CO": "America/Denver",
    "CT": "America/New_York",
    "DC": "America/New_York",
    "DE": "America/New_York",
    "FL": "America/New_York",
    "GA": "America/New_York",
    "HI": "Pacific/Honolulu",
    "IA": "America/Chicago",
    "ID": "America/Boise",
    "IL": "America/Chicago",
    "IN": "America/Indiana/Indianapolis",
    "KS": "America/Chicago",
    "KY": "America/New_York",
    "LA": "America/Chicago",
    "MA": "America/New_York",
    "MD": "America/New_York",
    "ME": "America/New_York",
    "MI": "America/Detroit",
    "MN": "America/Chicago",
    "MO": "America/Chicago",
    "MS": "America/Chicago",
    "MT": "America/Denver",
    "NC": "America/New_York",
    "ND": "America/Chicago",
    "NE": "America/Chicago",
    "NH": "America/New_York",
    "NJ": "America/New_York",
    "NM": "America/Denver",
    "NV": "America/Los_Angeles",
    "NY": "America/New_York",
    "OH": "America/New_York",
    "OK": "America/Chicago",
    "OR": "America/Los_Angeles",
    "PA": "America/New_York",
    "RI": "America/New_York",
    "SC": "America/New_York",
    "SD": "America/Chicago",
    "TN": "America/Chicago",
    "TX": "America/Chicago",
    "UT": "America/Denver",
    "VA": "America/New_York",
    "VT": "America/New_York",
    "WA": "America/Los_Angeles",
    "WI": "America/Chicago",
    "WV": "America/New_York",
    "WY": "America/Denver",
}


# ─── Claude-powered source discovery ─────────────────────────────────────────

def discover_event_sources(city: str, state: str, state_abbr: str) -> list[dict]:
    """
    Use Claude to generate the 6 best event source URLs for a city.
    Returns list of source dicts matching EventSource schema.
    """
    city_slug = city.lower().replace(" ", "-")
    state_lower = state.lower().replace(" ", "-")

    prompt = f"""Generate a JSON array of the 6 best local event sources for {city}, {state} ({state_abbr}).

For each source, provide realistic URLs that likely exist for this city. Include:
1. Eventbrite city page
2. City/county government events calendar
3. Local newspaper or alt-weekly events section
4. Visit[City] or tourism board events page
5. One major local venue (concert hall, amphitheater, arts center)
6. One local Facebook Events alternative or community calendar

For each source use this schema:
{{
  "name": "Source Name",
  "url": "https://actual-likely-url.com/events",
  "type": "eventbrite|city_calendar|news_events|alt_weekly|tourism|venue"
}}

Use real, plausible URLs based on your knowledge of {city}.
Return ONLY the JSON array, no explanation."""

    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    try:
        sources = json.loads(raw)
        return sources
    except json.JSONDecodeError:
        logger.warning("Claude source discovery JSON parse failed — using template defaults")
        return [
            {
                "name": f"Eventbrite {city}",
                "url": f"https://www.eventbrite.com/d/{state_lower}--{city_slug}/events/",
                "type": "eventbrite",
            },
            {
                "name": f"Visit {city} Events",
                "url": f"https://www.visit{city_slug.replace('-', '')}.com/events/",
                "type": "tourism",
            },
        ]


def discover_neighborhoods(city: str, state: str) -> list[str]:
    """Use Claude to list 5 notable neighborhoods for real estate spotlight rotation."""
    prompt = f"""List the 5 most well-known and desirable neighborhoods in {city}, {state} for a real estate spotlight in a local newsletter.

Return ONLY a JSON array of neighborhood name strings. Example: ["Downtown", "North End", "Westside"]"""

    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    try:
        return json.loads(raw)
    except Exception:
        return ["Downtown", "North Side", "East Side", "West End", "Midtown"]


# ─── Config Generation ────────────────────────────────────────────────────────

def create_city_config(
    city: str,
    state: str,
    state_abbr: str,
    timezone: Optional[str] = None,
) -> dict:
    """Generate a complete city config dict."""
    slug = city.lower().replace(" ", "-").replace("'", "")
    tz = timezone or TIMEZONE_DEFAULTS.get(state_abbr.upper(), "America/Chicago")
    city_slug_url = city.lower().replace(" ", "")

    logger.info(f"Discovering event sources for {city}...")
    sources = discover_event_sources(city, state, state_abbr)

    logger.info(f"Discovering neighborhoods for {city}...")
    neighborhoods = discover_neighborhoods(city, state)

    return {
        "city": city,
        "state": state,
        "state_abbr": state_abbr.upper(),
        "slug": slug,
        "newsletter_name": f"What's Up {city}",
        "tagline": f"Your weekly guide to the best of {city}",
        "greeting": f"Hey {city} fam!",
        "timezone": tz,
        "beehiiv_publication_id": "YOUR_BEEHIIV_PUBLICATION_ID",
        "send_day": "thursday",
        "send_hour": 7,
        "event_sources": sources,
        "real_estate": {
            "zillow_search_url": f"https://www.zillow.com/{slug}-{state_abbr.lower()}/",
            "market_area": f"{city}, {state_abbr}",
            "featured_neighborhoods": neighborhoods,
        },
        "social": {
            "facebook_group": "",
            "instagram": "",
            "twitter": "",
        },
    }


def create_city_sponsors(city: str) -> dict:
    """Generate a placeholder sponsors.json for a new city."""
    return {
        "_comment": f"What's Up {city} sponsor configuration.",
        "_packages": {
            "gold": {"annual_price": 10000, "placements": "Top of newsletter, dedicated block, social mention"},
            "silver": {"annual_price": 6000, "placements": "Mid-newsletter sponsor block"},
            "bronze": {"annual_price": 3000, "placements": "Footer sponsor mention"},
        },
        "sponsors": [
            {
                "name": "YOUR BUSINESS HERE",
                "tagline": f"Reach thousands of engaged {city} locals every Thursday morning.",
                "url": f"mailto:hello@whatsup{city.lower().replace(' ', '')}.com",
                "tier": "bronze",
                "active": True,
                "image_url": "",
                "promo_code": "",
                "cta_text": "Get in Touch",
                "category": "placeholder",
            }
        ],
    }


# ─── Revenue Extensions ───────────────────────────────────────────────────────

EXTENSION_CONFIGS = {
    "merch": {
        "provider": "printful",
        "store_url": "https://www.printful.com/dashboard",
        "products": ["t-shirt", "hoodie", "hat", "tote-bag", "mug"],
        "integration": "Add merch section to newsletter wrap-up block",
        "note": "Create Printful account, design logo products, add store_url to city config",
    },
    "events": {
        "frequency": "monthly",
        "suggested_events": ["happy hour", "trivia night", "local market pop-up"],
        "ticket_platform": "eventbrite",
        "revenue_estimate": "$2,000/month at 50-100 attendees",
        "note": "Host 1 community event/month. Sell tickets via Eventbrite. Sponsors welcome.",
    },
    "premium": {
        "beehiiv_tier": "premium",
        "annual_price": 99,
        "perks": ["early access", "bonus weekly digest", "local deals", "advertiser spotlights"],
        "note": "Enable beehiiv premium tier in publication settings",
    },
    "coupon-book": {
        "frequency": "seasonal",
        "price_per_business": 300,
        "suggested_slots": 20,
        "revenue_potential": "$6,000/season",
        "distribution": "PDF download for subscribers",
        "note": "Sell 20 local businesses a $300 slot in a seasonal digital coupon book",
    },
    "dashboard": {
        "type": "multi-city holding dashboard",
        "note": "Run python scale_module.py --dashboard to generate a simple revenue tracking dashboard",
    },
}


def add_extension(city_slug: str, extension: str):
    """Add a revenue extension to a city config."""
    config_path = CITIES_DIR / city_slug / "config.json"
    if not config_path.exists():
        logger.error(f"City {city_slug} not found. Run --city first.")
        return

    with open(config_path) as f:
        config = json.load(f)

    if "extensions" not in config:
        config["extensions"] = {}

    ext_data = EXTENSION_CONFIGS.get(extension)
    if not ext_data:
        logger.error(f"Unknown extension: {extension}. Available: {list(EXTENSION_CONFIGS.keys())}")
        return

    config["extensions"][extension] = ext_data
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    logger.info(f"Extension '{extension}' added to {city_slug}")
    logger.info(f"Note: {ext_data.get('note', '')}")


# ─── Dashboard ────────────────────────────────────────────────────────────────

def generate_dashboard():
    """Print a simple multi-city status dashboard."""
    cities = [d.name for d in CITIES_DIR.iterdir() if d.is_dir() and (d / "config.json").exists()]

    print("\n" + "=" * 60)
    print("  WHAT'S UP [CITY] — HOLDING COMPANY DASHBOARD")
    print("=" * 60)
    print(f"  Total cities configured: {len(cities)}")
    print()

    for slug in sorted(cities):
        config_path = CITIES_DIR / slug / "config.json"
        with open(config_path) as f:
            cfg = json.load(f)

        sponsors_path = CITIES_DIR / slug / "sponsors.json"
        sponsor_count = 0
        if sponsors_path.exists():
            with open(sponsors_path) as f:
                s_data = json.load(f)
            sponsor_count = sum(1 for s in s_data.get("sponsors", []) if s.get("active") and s.get("category") != "placeholder")

        extensions = list(cfg.get("extensions", {}).keys())
        print(f"  📍 {cfg['newsletter_name']} ({cfg['state_abbr']})")
        print(f"     beehiiv: {'✓ configured' if cfg.get('beehiiv_publication_id') != 'YOUR_BEEHIIV_PUBLICATION_ID' else '⚠ not configured'}")
        print(f"     Sponsors: {sponsor_count} active")
        print(f"     Extensions: {', '.join(extensions) if extensions else 'none'}")
        print()

    print("  REVENUE POTENTIAL (at full build-out):")
    print("  • 5,000 subs × $1/sub/month = $5,000/month per city")
    print("  • 5 cities = $25,000/month = $300,000/year")
    print("  • Add merch + events + premium = $500k+ potential")
    print("=" * 60)


# ─── Main CLI ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="What's Up [CITY] — Scale module: clone system for new cities"
    )
    parser.add_argument("--city", help="City name (e.g. 'Portland')")
    parser.add_argument("--state", help="Full state name (e.g. 'Oregon')")
    parser.add_argument("--state-abbr", help="State abbreviation (e.g. 'OR')")
    parser.add_argument("--timezone", help="Override timezone (e.g. 'America/Los_Angeles')")
    parser.add_argument("--extension", choices=list(EXTENSION_CONFIGS.keys()), help="Add a revenue extension to an existing city")
    parser.add_argument("--list", action="store_true", help="List all configured cities")
    parser.add_argument("--dashboard", action="store_true", help="Show multi-city dashboard")
    args = parser.parse_args()

    if args.list or args.dashboard:
        generate_dashboard()
        return

    if args.extension:
        if not args.city:
            logger.error("Specify --city SLUG to add an extension")
            sys.exit(1)
        slug = args.city.lower().replace(" ", "-")
        add_extension(slug, args.extension)
        return

    if not all([args.city, args.state, args.state_abbr]):
        parser.print_help()
        print("\nExample: python scale_module.py --city Portland --state Oregon --state-abbr OR")
        sys.exit(1)

    city = args.city
    state = args.state
    state_abbr = args.state_abbr
    slug = city.lower().replace(" ", "-").replace("'", "")
    city_dir = CITIES_DIR / slug

    if city_dir.exists():
        logger.warning(f"City '{slug}' already exists at {city_dir}")
        logger.warning("Delete the directory or choose a different city name.")
        sys.exit(1)

    city_dir.mkdir(parents=True)
    logger.info(f"Creating What's Up {city} configuration...")

    # Generate config
    config = create_city_config(city, state, state_abbr, args.timezone)
    config_path = city_dir / "config.json"
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    logger.info(f"✓ Config created: {config_path}")

    # Generate sponsors
    sponsors = create_city_sponsors(city)
    sponsors_path = city_dir / "sponsors.json"
    with open(sponsors_path, "w") as f:
        json.dump(sponsors, f, indent=2)
    logger.info(f"✓ Sponsors template created: {sponsors_path}")

    # Print next steps
    print(f"""
{'='*60}
✅  What's Up {city} is ready to launch!
{'='*60}

NEXT STEPS:
  1. Set CITY_SLUG={slug} in your .env file
  2. Create a new beehiiv publication for "{config['newsletter_name']}"
  3. Add your beehiiv publication ID to:
       cities/{slug}/config.json → "beehiiv_publication_id"
  4. Run a test: python main.py --city {slug} --dry-run
  5. Review the draft in: drafts/
  6. Schedule the first real run: python main.py --city {slug}

GROWTH LEVERS:
  • Run Facebook/Instagram ads targeting {city} residents
  • Post in local Facebook groups with a "What's happening this weekend" teaser
  • Partner with 1 local business for a free first-month sponsorship

REVENUE EXTENSIONS (add anytime):
  python scale_module.py --city {slug} --extension merch
  python scale_module.py --city {slug} --extension events
  python scale_module.py --city {slug} --extension premium

EVENT SOURCES CONFIGURED:
""")
    for src in config["event_sources"]:
        print(f"  • {src['name']}: {src['url']}")

    print(f"""
Full dashboard: python scale_module.py --dashboard
{'='*60}
""")


if __name__ == "__main__":
    main()
