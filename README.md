# FIFA World Cup 2026 — Prediction Game

A full-stack web app for predicting match scores across all 104 games of the 2026 FIFA World Cup. Players log in with Discord, submit predictions before kickoff, and earn points based on accuracy.

## Features

- **Discord OAuth** login
- **Score predictions** for all 104 matches — locked 5 minutes before kickoff
- **Points system** with outcome and exact-score tiers, plus a rarity bonus for uncommon scorelines
- **Leaderboard** with live standings
- **Match detail view** showing all players' predictions (revealed after kickoff)
- **Group standings** computed live from entered results
- **Knockout bracket** auto-populated from group stage results
- **Admin panel** to enter results manually or sync automatically via API-Football
- **English / French** UI

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

A **rarity bonus** applies when fewer than 5% of players predicted the same exact score: +5 pts (group stage) or +10 pts (knockout rounds).

## Stack

- **Backend:** Python / Flask, SQLite, APScheduler
- **Frontend:** Vanilla JS, single HTML file, no build step
- **Auth:** Discord OAuth2
- **Score sync:** [API-Football](https://www.api-football.com/) (optional)

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

Copy `.env.example` to `.env` and fill in the values:

```
DISCORD_CLIENT_ID=
DISCORD_CLIENT_SECRET=
DISCORD_REDIRECT_URI=https://yourdomain.com/auth/discord/callback
ADMIN_DISCORD_IDS=123456789,987654321
API_FOOTBALL_KEY=          # optional — enables automatic score sync
CRON_SECRET=               # optional — secures the /api/cron/sync-scores endpoint
```

### 3. Run

```bash
python app.py
```

The app starts on `http://0.0.0.0:8026`.

### Production (Passenger / Gunicorn)

The app is configured for Passenger via `passenger_wsgi.py`. For Gunicorn:

```bash
gunicorn app:app
```

## Admin

Admins (Discord IDs listed in `ADMIN_DISCORD_IDS`) can:

- Enter match results manually from the match cards
- Trigger a score sync from the leaderboard modal
- Set API-Football fixture IDs via `POST /api/admin/external-ids`

Automatic score sync runs hourly once `API_FOOTBALL_KEY` is set, polling matches that kicked off at least 115 minutes ago.
