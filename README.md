# What's Up [CITY] — Automated Local Newsletter System

> Modeled on Naptown Scoop ($300k/yr), Catskill Crew ($57k/mo), Winnipeg Digest ($60k in 2 months), and the multi-city "What's Up" series.

A fully automated, modular local newsletter system that scrapes local events, generates polished content with Claude AI, and sends a weekly newsletter via beehiiv — every Thursday morning on autopilot.

**Current market:** Boise, Idaho → `What's Up Boise`

---

## Architecture

```
main.py                  ← Weekly orchestrator (Claude Opus 4.6)
├── scrape_events.py     ← Parallel Firecrawl scraping of 6+ sources
├── generate_content.py  ← Claude Sonnet 4.6 content generation
├── build_newsletter.py  ← Mobile-responsive HTML renderer
└── send_newsletter.py   ← beehiiv API create + schedule

config.py                ← Config loader (cities, sponsors, env)
scale_module.py          ← One-command new city clone

cities/
└── boise/
    ├── config.json      ← City settings + event sources
    └── sponsors.json    ← Sponsor definitions + pricing

.github/
└── workflows/
    └── newsletter.yml   ← Thursday 7 AM autopilot via GitHub Actions

drafts/                  ← HTML drafts saved here before send
logs/                    ← Run logs
```

---

## Quick Start

### 1. Clone & install

```bash
git clone <this-repo>
cd little-big-city-news
pip install -r requirements.txt
```

### 2. Configure API keys

```bash
cp .env.example .env
# Edit .env with your keys:
# - ANTHROPIC_API_KEY (console.anthropic.com)
# - BEEHIIV_API_KEY (app.beehiiv.com → Settings → API)
# - FIRECRAWL_API_KEY (firecrawl.dev — free tier: 500 pages)
```

### 3. Configure beehiiv publication ID

1. Create a publication at [beehiiv.com](https://beehiiv.com)
2. Go to Settings → Publication → copy the Publication ID
3. Paste it into `cities/boise/config.json` → `"beehiiv_publication_id"`

### 4. Test with a dry run

```bash
python main.py --dry-run
# Builds the newsletter, saves HTML to drafts/ — does NOT send to beehiiv
# Open the HTML file in your browser to preview
```

### 5. Send your first newsletter

```bash
python main.py
# Scrapes events, generates content, creates beehiiv draft, schedules for Thursday 7 AM MT
```

---

## Sponsor Packages

Edit `sponsors.json` (or `cities/boise/sponsors.json`) to add real sponsors.

| Tier   | Annual Price | Placement |
|--------|-------------|-----------|
| Gold   | $10,000/yr  | Top of newsletter, dedicated block, social mentions, category exclusive |
| Silver | $6,000/yr   | Mid-newsletter block with logo + tagline + CTA |
| Bronze | $3,000/yr   | Footer mention with link |

**Real estate focus:** Real estate agents are the #1 sponsor category for local newsletters. Offer an exclusive real estate sponsor slot at the Gold tier + featured home block ownership.

**Sponsor intake:** Point prospects to reply to any newsletter issue or email you directly. The system handles placement via `sponsors.json`.

---

## Autopilot via GitHub Actions

The system runs automatically every Thursday at 5 AM UTC (covers 7 AM MT / 9 AM ET sends).

### Setup GitHub Secrets

In your GitHub repo → Settings → Secrets and variables → Actions:

**Secrets (sensitive):**
- `ANTHROPIC_API_KEY`
- `BEEHIIV_API_KEY`
- `FIRECRAWL_API_KEY`

**Variables (non-sensitive):**
- `CITY_SLUG` = `boise`
- `HUMAN_APPROVAL` = `none` (or `local` or `email`)

### Manual trigger

Go to Actions → Weekly Newsletter → Run workflow. Can run with `--dry-run` for safe testing.

---

## Scaling to New Cities

```bash
# Clone the entire system for a new city in one command:
python scale_module.py --city "Portland" --state "Oregon" --state-abbr "OR"

# View all configured cities:
python scale_module.py --list

# Multi-city dashboard:
python scale_module.py --dashboard
```

Claude automatically discovers the best event sources for each city.

Then in `.env` or GitHub Actions variable, set `CITY_SLUG=portland`.

For multi-city GitHub Actions, uncomment the matrix strategy in `.github/workflows/newsletter.yml`.

---

## Revenue Extensions

Add revenue modules to any city with one command:

```bash
python scale_module.py --city boise --extension merch       # Printful/Printify merch store
python scale_module.py --city boise --extension events      # Monthly community events ($2k/mo)
python scale_module.py --city boise --extension premium     # beehiiv premium tier ($99/yr)
python scale_module.py --city boise --extension coupon-book # Seasonal coupon book ($6k/season)
```

---

## Growth Strategy (Facebook Ads)

The fastest growth lever is Facebook/Instagram ads targeting local residents.

**Proven approach (Winnipeg Digest grew to 40k subs in 8 months):**

1. **Ad creative:** "Are you a [City] local? Here's your free weekly guide to what's happening this weekend →"
2. **Target:** City + 25 mile radius, age 25-55, interests: local events, community, restaurants
3. **Budget:** Start at $5-10/day. At $1-3 cost per subscriber, $300/mo ad spend = 100-300 new subs
4. **Landing page:** Your beehiiv subscribe page
5. **Referral:** Enable beehiiv's built-in referral program for organic word-of-mouth

**Content growth:**
- Post the "top 3 events this weekend" as a teaser in local Facebook Groups (no spam — add genuine value)
- Partner with local businesses for cross-promotion (free newsletter feature in exchange for social share)
- Instagram Reels with "What's happening in [City] this weekend" using event highlights

---

## Newsletter Format

Every issue follows this structure (Naptown Scoop polish + What's Up Edmond scannability):

```
Header + Date
Greeting + Intro (warm, local, 80 words max)
Trivia Teaser (answer at bottom)
Featured Home: "Guess the price!" (Zillow hook)
Sponsor Block(s)
──────────────────────
Thursday events (with Where / Starts / Cost / Link)
Friday events
Saturday events
Sunday events
──────────────────────
Real Estate Spotlight (neighborhood feature)
Trivia Answer
Wrap-up (tip jar + archive + refer-a-friend)
Footer (unsubscribe / view in browser)
```

**Editorial rules (Naptown Scoop model):**
- ✅ Festivals, concerts, markets, classes, sports, art, food, outdoor
- ✅ Free AND ticketed events
- ✅ Family-friendly by default
- ❌ No politics, no crime, no arrests, no controversy
- ❌ No events outside the metro area

---

## File Reference

| File | Purpose |
|------|---------|
| `main.py` | Weekly orchestrator — run this |
| `scrape_events.py` | Parallel Firecrawl event scraper |
| `generate_content.py` | Claude content generator |
| `build_newsletter.py` | HTML newsletter renderer |
| `send_newsletter.py` | beehiiv API integration |
| `config.py` | Config loader |
| `scale_module.py` | New city clone tool |
| `cities/boise/config.json` | Boise city config |
| `cities/boise/sponsors.json` | Boise sponsor config |
| `sponsors.json` | Default sponsor config |
| `.env.example` | Environment variable template |
| `.github/workflows/newsletter.yml` | Thursday autopilot workflow |

---

## Revenue Model (6-month targets)

Based on Naptown Scoop / Winnipeg Digest benchmarks:

| Metric | Month 1 | Month 3 | Month 6 |
|--------|---------|---------|---------|
| Subscribers | 200 | 1,500 | 5,000 |
| Sponsors | 1 (placeholder) | 2-3 paying | 4-5 paying |
| Monthly revenue | $0 | $1,500 | $5,000+ |
| Annual run rate | — | $18k | $60k+ |

At 5 cities: $300k+/year potential.

---

*Built with Claude Opus 4.6 orchestration + Claude Sonnet 4.6 content generation + Firecrawl scraping + beehiiv delivery.*
