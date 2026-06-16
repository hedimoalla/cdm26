# FIFA World Cup 2026 — Prediction Game

A full-stack web app for predicting match scores across all 104 games of the 2026 FIFA World Cup. Players log in with Discord or Google, submit predictions before kickoff, and earn points based on accuracy.

## Features

- **Discord & Google OAuth** login
- **Score predictions** for all 104 matches — locked 5 minutes before kickoff
- **Points system** with outcome and exact-score tiers, plus a rarity bonus for uncommon scorelines
- **Leaderboard** with live standings and individual player profile pages
- **Match detail view** showing all players' predictions (revealed after kickoff), prediction distribution bar, and exact score highlights
- **Group standings** computed live from entered results (FIFA rank tiebreaker)
- **Knockout bracket** auto-populated from group stage results
- **Admin panel** to enter live / half-time / final scores per match, or sync automatically via football-data.org
- **Hide predictions** toggle for screen sharing
- **Auto-scroll** to today's matches on page load
- **Previous / Next** match navigation in detail view
- **English / French** UI (persisted in localStorage)
- **Terms & Conditions** page at `/terms`

## Points

| Stage | Correct Outcome | Exact Score |
|---|---|---|
| Group Stage | 1 pt | 3 pts |
| Round of 32 | 3 pts | 6 pts |
| Round of 16 | 3 pts | 6 pts |
| Quarterfinals | 5 pts | 7 pts |
| Semifinals | 7 pts | 15 pts |
| 3rd Place | 7 pts | 15 pts |
| Final | 10 pts | 20 pts |

A **rarity bonus** applies when fewer than 15% of players (group stage) or 12% (knockout) predicted the same exact scoreline: +5 pts (group) or +10 pts (knockout).

## Stack

- **Backend:** Python / Flask, SQLite (WAL mode), APScheduler
- **Frontend:** Vanilla JS, single HTML file (`static/index.html`), no build step
- **Auth:** Discord OAuth2 + Google OAuth2; 30-day persistent sessions
- **Score sync:** [football-data.org](https://www.football-data.org/) free tier (auto-syncs FINISHED results; live scores entered manually by admin)
- **Hosting:** Render (persistent disk at `/var/data/wc2026.db`)

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

Copy `.env.example` to `.env` and fill in:

```
DISCORD_CLIENT_ID=
DISCORD_CLIENT_SECRET=
DISCORD_REDIRECT_URI=https://yourdomain.com/auth/discord/callback

GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=https://yourdomain.com/auth/google/callback

ADMIN_DISCORD_IDS=123456789,987654321

FOOTBALL_DATA_KEY=          # football-data.org API token
DB_PATH=/var/data/wc2026.db # path to persistent SQLite DB (Render disk)
CRON_SECRET=                # secures /api/cron/sync-scores
RESTORE_SECRET=             # secures DB restore endpoint
```

### 3. Run

```bash
python app.py
```

### Production (Gunicorn)

```bash
gunicorn app:app
```

## Admin

Admins (Discord IDs listed in `ADMIN_DISCORD_IDS`) see extra controls on each match card:

- **LIVE** (blue) — enter current score without locking predictions
- **HT** (yellow) — mark match as half-time
- **FT** (orange) — lock final score and trigger point calculation
- **✕** — clear a result
- **Sync Scores Now** button in the leaderboard — manually trigger a football-data.org sync

The scheduler polls football-data.org every 2 minutes during active match windows. Note: the free tier does not provide real-time live data — matches stay `TIMED` in the API during play and only update to `FINISHED` after the match ends (with up to a few hours' delay).

## Branching

- `main` — production branch, auto-deploys on Render
- `dev` — active development branch
