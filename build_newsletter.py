"""
build_newsletter.py — Renders the final mobile-responsive beehiiv HTML newsletter.

Layout (Naptown Scoop polish + What's Up Edmond scannability):
  1. Header with newsletter name + date
  2. Greeting + intro
  3. Trivia teaser
  4. Featured Home ("Guess the price!")
  5. Sponsor block(s) — Gold first, then Silver
  6. Events: Thursday → Friday → Saturday → Sunday
  7. Real Estate Spotlight
  8. Wrap-up: trivia answer + tip jar + archive
  9. Footer
"""

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from config import (
    CityConfig,
    Event,
    Sponsor,
    NewsletterContext,
    load_city_config,
    load_sponsors,
)

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
DRAFTS_DIR = BASE_DIR / "drafts"
DRAFTS_DIR.mkdir(exist_ok=True)


# ─── Color Palette ────────────────────────────────────────────────────────────
# Clean, modern, works across email clients

COLORS = {
    "bg": "#f9f9f7",
    "card": "#ffffff",
    "primary": "#1a1a2e",       # deep navy
    "accent": "#e63946",        # bold red
    "accent_light": "#fff0f1",
    "text": "#2d2d2d",
    "text_light": "#6b7280",
    "border": "#e5e7eb",
    "event_bg": "#f8fafc",
    "thursday": "#dbeafe",      # blue tint
    "friday": "#dcfce7",        # green tint
    "saturday": "#fef9c3",      # yellow tint
    "sunday": "#fce7f3",        # pink tint
    "sponsor_bg": "#fffbeb",
    "re_bg": "#f0fdf4",
    "trivia_bg": "#f0f4ff",
    "footer": "#374151",
}

DAY_COLORS = {
    "Thursday": COLORS["thursday"],
    "Friday": COLORS["friday"],
    "Saturday": COLORS["saturday"],
    "Sunday": COLORS["sunday"],
}

CATEGORY_EMOJI = {
    "music": "🎵",
    "food": "🍽️",
    "family": "👨‍👩‍👧",
    "arts": "🎨",
    "sports": "⚽",
    "community": "🤝",
    "outdoor": "🌲",
    "default": "📅",
}


# ─── HTML Components ──────────────────────────────────────────────────────────

def css_reset() -> str:
    return """
<style>
  body { margin: 0; padding: 0; background-color: #f9f9f7; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }
  table { border-collapse: collapse; mso-table-lspace: 0pt; mso-table-rspace: 0pt; }
  img { border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; max-width: 100%; }
  a { color: #e63946; }
  @media only screen and (max-width: 600px) {
    .container { width: 100% !important; }
    .mobile-pad { padding: 16px !important; }
    .mobile-hide { display: none !important; }
    .mobile-full { width: 100% !important; }
  }
</style>"""


def header_block(ctx: NewsletterContext) -> str:
    city = ctx.city_config.city
    name = ctx.city_config.newsletter_name
    tagline = ctx.city_config.tagline
    pub_date = ctx.publish_date or date.today().strftime("%B %d, %Y")

    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0">
  <tr>
    <td align="center" style="background-color:{COLORS['primary']}; padding: 28px 24px 20px;">
      <h1 style="margin:0; color:#ffffff; font-size:32px; font-weight:800; letter-spacing:-0.5px;">{name}</h1>
      <p style="margin:6px 0 0; color:#a5b4fc; font-size:14px; letter-spacing:1px; text-transform:uppercase;">{tagline}</p>
      <p style="margin:10px 0 0; color:#e5e7eb; font-size:13px;">{pub_date}</p>
    </td>
  </tr>
</table>"""


def intro_block(ctx: NewsletterContext) -> str:
    intro = ctx.intro_text or f"Hey {ctx.city_config.city} fam! Here's what's happening this weekend. 👇"
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0">
  <tr>
    <td class="mobile-pad" style="background-color:{COLORS['card']}; padding:28px 32px 20px;">
      <p style="margin:0; color:{COLORS['text']}; font-size:17px; line-height:1.7;">{intro}</p>
    </td>
  </tr>
</table>"""


def trivia_teaser_block(ctx: NewsletterContext) -> str:
    question = ctx.trivia_question or "What makes this city so special?"
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0">
  <tr>
    <td class="mobile-pad" style="background-color:{COLORS['trivia_bg']}; padding:20px 32px; border-left:4px solid #6366f1;">
      <p style="margin:0 0 4px; color:#6366f1; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:1px;">🧠 Today's Trivia</p>
      <p style="margin:0; color:{COLORS['text']}; font-size:16px; font-weight:600; line-height:1.5;">{question}</p>
      <p style="margin:6px 0 0; color:{COLORS['text_light']}; font-size:13px; font-style:italic;">Answer at the bottom of this email ↓</p>
    </td>
  </tr>
</table>"""


def featured_home_block(ctx: NewsletterContext) -> str:
    home = ctx.featured_home
    if not home:
        return ""

    city = ctx.city_config.city
    address = home.get("address", f"A mystery home in {city}")
    price = home.get("price", "???")
    beds = home.get("beds", "")
    baths = home.get("baths", "")
    sqft = home.get("sqft", "")
    url = home.get("zillow_url", ctx.city_config.real_estate.zillow_search_url)
    is_placeholder = home.get("is_placeholder", True)

    details_parts = []
    if beds:
        details_parts.append(f"{beds} bed")
    if baths:
        details_parts.append(f"{baths} bath")
    if sqft:
        details_parts.append(sqft)
    details = " · ".join(details_parts)

    price_display = "???" if is_placeholder else price
    cta = "Guess the price!" if is_placeholder else f"Listed at {price}"

    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0">
  <tr>
    <td class="mobile-pad" style="background-color:{COLORS['card']}; padding:24px 32px;">
      <p style="margin:0 0 4px; color:{COLORS['accent']}; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:1px;">🏡 Featured Home</p>
      <h2 style="margin:4px 0 8px; color:{COLORS['primary']}; font-size:20px; font-weight:700;">What Would You Guess This {city} Home Costs?</h2>
      {"<p style='margin:0 0 6px; color:" + COLORS['text'] + "; font-size:15px;'>" + address + "</p>" if address else ""}
      {"<p style='margin:0 0 12px; color:" + COLORS['text_light'] + "; font-size:14px;'>" + details + "</p>" if details else ""}
      <a href="{url}" style="display:inline-block; background-color:{COLORS['accent']}; color:#ffffff; text-decoration:none; font-size:15px; font-weight:700; padding:12px 24px; border-radius:8px;">{cta} →</a>
    </td>
  </tr>
</table>"""


def sponsor_block(sponsor: Sponsor) -> str:
    cta = sponsor.cta_text or "Learn More"
    promo = f"<p style='margin:4px 0 0; color:#92400e; font-size:13px;'>Use code <strong>{sponsor.promo_code}</strong> for a special offer!</p>" if sponsor.promo_code else ""
    img_html = f"<img src='{sponsor.image_url}' alt='{sponsor.name}' style='max-width:120px; margin-bottom:12px;'><br>" if sponsor.image_url else ""

    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0">
  <tr>
    <td class="mobile-pad" style="background-color:{COLORS['sponsor_bg']}; padding:20px 32px; border:1px solid #fde68a; border-radius:0;">
      <p style="margin:0 0 6px; color:#92400e; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:1px;">✨ Sponsored</p>
      {img_html}
      <p style="margin:0 0 4px; color:{COLORS['primary']}; font-size:17px; font-weight:700;">{sponsor.name}</p>
      <p style="margin:0 0 10px; color:{COLORS['text']}; font-size:15px; line-height:1.6;">{sponsor.tagline}</p>
      {promo}
      <a href="{sponsor.url}" style="display:inline-block; background-color:{COLORS['primary']}; color:#ffffff; text-decoration:none; font-size:14px; font-weight:600; padding:10px 20px; border-radius:6px; margin-top:10px;">{cta} →</a>
    </td>
  </tr>
</table>"""


def event_card(event: Event) -> str:
    emoji = CATEGORY_EMOJI.get(event.category, CATEGORY_EMOJI["default"])
    time_str = event.start_time
    if event.end_time:
        time_str += f" – {event.end_time}"
    cost_color = "#16a34a" if event.cost.lower() == "free" else COLORS["text"]
    link_html = f'<a href="{event.url}" style="color:{COLORS["accent"]}; font-size:13px; font-weight:600; text-decoration:none;">Get tickets / more info →</a>' if event.url else ""

    return f"""
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:12px; background:{COLORS['event_bg']}; border-radius:8px; border:1px solid {COLORS['border']};">
    <tr>
      <td style="padding:14px 16px;">
        <p style="margin:0 0 2px; font-size:11px; color:{COLORS['text_light']}; text-transform:uppercase; letter-spacing:0.5px;">{emoji} {event.category.title()}</p>
        <p style="margin:0 0 6px; font-size:16px; font-weight:700; color:{COLORS['primary']};">{event.title}</p>
        <p style="margin:0 0 6px; font-size:14px; color:{COLORS['text']}; line-height:1.5;">{event.description}</p>
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td style="font-size:13px; color:{COLORS['text_light']};">
              📍 <strong>{event.location}</strong>{(' — ' + event.address) if event.address else ''}<br>
              🕐 {time_str}<br>
              💰 <span style="color:{cost_color}; font-weight:600;">{event.cost}</span>
            </td>
          </tr>
        </table>
        {"<p style='margin:8px 0 0;'>" + link_html + "</p>" if link_html else ""}
      </td>
    </tr>
  </table>"""


def events_section(day: str, events: list[Event]) -> str:
    if not events:
        return ""

    bg_color = DAY_COLORS.get(day, COLORS["card"])
    cards = "\n".join(event_card(ev) for ev in events)
    count_label = f"{len(events)} event{'s' if len(events) != 1 else ''}"

    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0">
  <tr>
    <td class="mobile-pad" style="background-color:{COLORS['card']}; padding:24px 32px 16px;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{bg_color}; border-radius:8px; padding:0; overflow:hidden;">
        <tr>
          <td style="padding:14px 16px 10px; border-bottom:1px solid {COLORS['border']};">
            <h3 style="margin:0; color:{COLORS['primary']}; font-size:20px; font-weight:800;">{day}</h3>
            <p style="margin:2px 0 0; color:{COLORS['text_light']}; font-size:13px;">{count_label} this {day.lower()}</p>
          </td>
        </tr>
        <tr>
          <td style="padding:12px 12px 4px;">
            {cards}
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>"""


def real_estate_block(ctx: NewsletterContext) -> str:
    re = ctx.real_estate_spotlight
    if not re:
        return ""

    neighborhood = re.get("neighborhood", "")
    market_blurb = re.get("market_blurb", "")
    spotlight = re.get("neighborhood_spotlight", "")
    zillow_url = ctx.city_config.real_estate.zillow_search_url

    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0">
  <tr>
    <td class="mobile-pad" style="background-color:{COLORS['re_bg']}; padding:24px 32px;">
      <p style="margin:0 0 4px; color:#15803d; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:1px;">🏠 Real Estate Spotlight</p>
      <h2 style="margin:4px 0 12px; color:{COLORS['primary']}; font-size:20px; font-weight:700;">{neighborhood + ' Neighborhood' if neighborhood else ctx.city_config.city + ' Real Estate'}</h2>
      {"<p style='margin:0 0 12px; color:" + COLORS['text'] + "; font-size:15px; line-height:1.7;'>" + market_blurb + "</p>" if market_blurb else ""}
      {"<p style='margin:0 0 16px; color:" + COLORS['text'] + "; font-size:15px; line-height:1.7;'><strong>Neighborhood Spotlight:</strong> " + spotlight + "</p>" if spotlight else ""}
      <a href="{zillow_url}" style="display:inline-block; background-color:#15803d; color:#ffffff; text-decoration:none; font-size:14px; font-weight:600; padding:10px 20px; border-radius:6px;">Browse Listings →</a>
    </td>
  </tr>
</table>"""


def trivia_answer_block(ctx: NewsletterContext) -> str:
    answer = ctx.trivia_answer or "Thanks for playing!"
    question = ctx.trivia_question or ""
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0">
  <tr>
    <td class="mobile-pad" style="background-color:{COLORS['trivia_bg']}; padding:20px 32px; border-left:4px solid #6366f1;">
      <p style="margin:0 0 4px; color:#6366f1; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:1px;">🧠 Trivia Answer</p>
      {"<p style='margin:0 0 6px; color:" + COLORS['text_light'] + "; font-size:14px; font-style:italic;'>You asked: " + question + "</p>" if question else ""}
      <p style="margin:0; color:{COLORS['primary']}; font-size:16px; font-weight:600; line-height:1.6;">{answer}</p>
    </td>
  </tr>
</table>"""


def wrapup_block(ctx: NewsletterContext) -> str:
    city = ctx.city_config.city
    newsletter_name = ctx.city_config.newsletter_name
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0">
  <tr>
    <td class="mobile-pad" style="background-color:{COLORS['card']}; padding:24px 32px; text-align:center;">
      <p style="margin:0 0 8px; color:{COLORS['text']}; font-size:16px; line-height:1.7;">That's a wrap for this week! Have an amazing weekend, {city} 🎉</p>
      <p style="margin:0 0 16px; color:{COLORS['text_light']}; font-size:14px;">Know about an event we missed? Reply to this email and let us know!</p>
      <a href="https://ko-fi.com" style="display:inline-block; background-color:#ff5e5b; color:#ffffff; text-decoration:none; font-size:14px; font-weight:600; padding:10px 20px; border-radius:6px; margin-right:8px;">☕ Support {newsletter_name}</a>
      <a href="#" style="display:inline-block; background-color:{COLORS['primary']}; color:#ffffff; text-decoration:none; font-size:14px; font-weight:600; padding:10px 20px; border-radius:6px;">📚 View Archive</a>
      <p style="margin:16px 0 0; color:{COLORS['text_light']}; font-size:13px;">Refer a friend → they'll love you for it</p>
    </td>
  </tr>
</table>"""


def footer_block(ctx: NewsletterContext) -> str:
    newsletter_name = ctx.city_config.newsletter_name
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0">
  <tr>
    <td align="center" style="background-color:{COLORS['footer']}; padding:20px 24px;">
      <p style="margin:0 0 6px; color:#9ca3af; font-size:13px;">{newsletter_name} | Made with ❤️ for {ctx.city_config.city}</p>
      <p style="margin:0; color:#6b7280; font-size:12px;">
        <a href="{{{{unsubscribe_url}}}}" style="color:#6b7280;">Unsubscribe</a> ·
        <a href="{{{{browser_link}}}}" style="color:#6b7280;">View in browser</a>
      </p>
    </td>
  </tr>
</table>"""


def divider() -> str:
    return f'<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr><td style="padding:0; height:8px; background-color:{COLORS["bg"]};"></td></tr></table>'


# ─── Main Builder ─────────────────────────────────────────────────────────────

def build_newsletter_html(ctx: NewsletterContext) -> str:
    """Render the full newsletter HTML from a NewsletterContext."""
    from scrape_events import EventScraper
    scraper = EventScraper()
    grouped = scraper.group_by_day(ctx.events)

    # Sort sponsors: gold → silver → bronze
    tier_order = {"gold": 0, "silver": 1, "bronze": 2}
    active_sponsors = [s for s in ctx.sponsors if s.active]
    active_sponsors.sort(key=lambda s: tier_order.get(s.tier, 9))

    # Build sections
    sections = [
        css_reset(),
        header_block(ctx),
        divider(),
        intro_block(ctx),
        divider(),
        trivia_teaser_block(ctx),
        divider(),
        featured_home_block(ctx),
        divider(),
    ]

    # Add sponsors (up to 2 in main body)
    for sponsor in active_sponsors[:2]:
        sections.append(sponsor_block(sponsor))
        sections.append(divider())

    # Add event days
    for day in ["Thursday", "Friday", "Saturday", "Sunday"]:
        day_events = grouped.get(day, [])
        if day_events:
            sections.append(events_section(day, day_events))
            sections.append(divider())

    # Add real estate, trivia answer, wrapup
    sections.extend([
        real_estate_block(ctx),
        divider(),
        trivia_answer_block(ctx),
        divider(),
        wrapup_block(ctx),
        divider(),
        footer_block(ctx),
    ])

    body_content = "\n".join(s for s in sections if s)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<title>{ctx.city_config.newsletter_name} — {ctx.publish_date}</title>
</head>
<body style="margin:0; padding:0; background-color:{COLORS['bg']};">
<table class="container" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:680px; margin:0 auto; background-color:{COLORS['bg']};">
  <tr>
    <td>
{body_content}
    </td>
  </tr>
</table>
</body>
</html>"""

    return html


def save_draft(html: str, ctx: NewsletterContext) -> Path:
    """Save HTML draft to drafts/ directory. Returns file path."""
    slug = ctx.city_config.slug
    date_str = ctx.publish_date.replace(" ", "_").replace(",", "").replace("/", "-")
    filename = DRAFTS_DIR / f"{slug}_{date_str}.html"
    filename.write_text(html, encoding="utf-8")
    logger.info(f"Draft saved → {filename}")
    return filename


def build_subject_line(ctx: NewsletterContext) -> str:
    """Generate a compelling email subject line."""
    city = ctx.city_config.city
    event_count = len(ctx.events)
    week_range = ctx.week_range or "this weekend"

    candidates = [
        f"🎉 {event_count} things to do in {city} {week_range}",
        f"What's Up {city} — Your weekend guide is here!",
        f"This {city} weekend is stacked 🔥 ({event_count} picks inside)",
        f"Your {city} weekend starts here 👇",
    ]
    # Rotate based on week number
    idx = date.today().isocalendar().week % len(candidates)
    return candidates[idx]


if __name__ == "__main__":
    import asyncio
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    from config import load_city_config, load_sponsors
    from generate_content import generate_all_content

    city_config = load_city_config()
    sponsors = load_sponsors()

    content = generate_all_content(city_config=city_config, events=[], publish_date="March 20, 2026", week_range="March 20-23")
    ctx = NewsletterContext(
        city_config=city_config,
        sponsors=sponsors,
        events=[],
        trivia_question=content["trivia_question"],
        trivia_answer=content["trivia_answer"],
        intro_text=content["intro"],
        featured_home=content["featured_home"],
        real_estate_spotlight=content["real_estate_spotlight"],
        publish_date="March 20, 2026",
        week_range="March 20-23",
    )

    html = build_newsletter_html(ctx)
    path = save_draft(html, ctx)
    print(f"\nDraft saved to: {path}")
    print(f"Subject line: {build_subject_line(ctx)}")
