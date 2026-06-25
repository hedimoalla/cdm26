import os
import json
import secrets
import requests as req
from urllib.parse import urlencode
from flask import Flask, request, jsonify, session, send_from_directory, send_file, redirect
from flask_bcrypt import Bcrypt
import sqlite3
from contextlib import contextmanager
from dotenv import load_dotenv
from datetime import datetime, timedelta
import logging
import atexit
from apscheduler.schedulers.background import BackgroundScheduler

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

app = Flask(__name__, static_folder='static', static_url_path='')

app.config.update(
    SESSION_COOKIE_SECURE=bool(os.getenv('RENDER')),  # True on Render, False locally
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)

# Store the secret key on the persistent disk (same dir as DB) so it survives deploys.
# Locally (no DB_PATH set) falls back to the source directory.
_data_dir = os.path.dirname(os.getenv('DB_PATH', os.path.join(os.path.dirname(__file__), 'wc2026.db')))
_KEY_FILE = os.path.join(_data_dir, '.secret_key')
if os.path.exists(_KEY_FILE):
    with open(_KEY_FILE, 'rb') as _f:
        app.secret_key = _f.read()
else:
    app.secret_key = os.urandom(32)
    with open(_KEY_FILE, 'wb') as _f:
        _f.write(app.secret_key)

bcrypt = Bcrypt(app)

DISCORD_CLIENT_ID     = os.getenv('DISCORD_CLIENT_ID', '')
DISCORD_CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET', '')
DISCORD_REDIRECT_URI  = os.getenv('DISCORD_REDIRECT_URI', '')
ADMIN_IDS             = set(filter(None, os.getenv('ADMIN_DISCORD_IDS', '').split(',')))
FOOTBALL_DATA_KEY     = os.getenv('FOOTBALL_DATA_KEY', '')
CRON_SECRET           = os.getenv('CRON_SECRET', '')
RESTORE_SECRET        = os.getenv('RESTORE_SECRET', '')
GOOGLE_CLIENT_ID     = os.getenv('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET', '')
GOOGLE_REDIRECT_URI  = os.getenv('GOOGLE_REDIRECT_URI', '')

DB = os.getenv('DB_PATH', os.path.join(os.path.dirname(__file__), 'wc2026.db'))

# ── Match metadata (id, date, time_ET, stage) — all during EDT (UTC-4) ────────
_MATCH_META = [
    (1,'2026-06-11','15:00','group'),(2,'2026-06-11','22:00','group'),
    (3,'2026-06-12','15:00','group'),(4,'2026-06-12','21:00','group'),
    (5,'2026-06-13','15:00','group'),(6,'2026-06-13','18:00','group'),
    (7,'2026-06-13','21:00','group'),(8,'2026-06-13','00:00','group'),
    (9,'2026-06-14','13:00','group'),(10,'2026-06-14','16:00','group'),
    (11,'2026-06-14','19:00','group'),(12,'2026-06-14','22:00','group'),
    (13,'2026-06-15','12:00','group'),(14,'2026-06-15','15:00','group'),
    (15,'2026-06-15','18:00','group'),(16,'2026-06-15','21:00','group'),
    (17,'2026-06-16','15:00','group'),(18,'2026-06-16','18:00','group'),
    (19,'2026-06-16','21:00','group'),(20,'2026-06-17','00:00','group'),
    (21,'2026-06-17','13:00','group'),(22,'2026-06-17','16:00','group'),
    (23,'2026-06-17','19:00','group'),(24,'2026-06-17','22:00','group'),
    (25,'2026-06-18','12:00','group'),(26,'2026-06-18','15:00','group'),
    (27,'2026-06-18','18:00','group'),(28,'2026-06-18','21:00','group'),
    (29,'2026-06-19','15:00','group'),(30,'2026-06-19','18:00','group'),
    (31,'2026-06-19','21:00','group'),(32,'2026-06-20','00:00','group'),
    (33,'2026-06-20','13:00','group'),(34,'2026-06-20','16:00','group'),
    (35,'2026-06-20','20:00','group'),(36,'2026-06-21','00:00','group'),
    (37,'2026-06-21','12:00','group'),(38,'2026-06-21','15:00','group'),
    (39,'2026-06-21','18:00','group'),(40,'2026-06-21','21:00','group'),
    (41,'2026-06-22','13:00','group'),(42,'2026-06-22','17:00','group'),
    (43,'2026-06-22','20:00','group'),(44,'2026-06-22','23:00','group'),
    (45,'2026-06-23','13:00','group'),(46,'2026-06-23','16:00','group'),
    (47,'2026-06-23','19:00','group'),(48,'2026-06-23','22:00','group'),
    (49,'2026-06-24','15:00','group'),(50,'2026-06-24','15:00','group'),
    (51,'2026-06-24','18:00','group'),(52,'2026-06-24','18:00','group'),
    (53,'2026-06-24','21:00','group'),(54,'2026-06-24','21:00','group'),
    (55,'2026-06-25','16:00','group'),(56,'2026-06-25','16:00','group'),
    (57,'2026-06-25','19:00','group'),(58,'2026-06-25','19:00','group'),
    (59,'2026-06-25','22:00','group'),(60,'2026-06-25','22:00','group'),
    (61,'2026-06-26','15:00','group'),(62,'2026-06-26','15:00','group'),
    (63,'2026-06-26','20:00','group'),(64,'2026-06-26','20:00','group'),
    (65,'2026-06-26','23:00','group'),(66,'2026-06-26','23:00','group'),
    (67,'2026-06-27','17:00','group'),(68,'2026-06-27','17:00','group'),
    (69,'2026-06-27','19:30','group'),(70,'2026-06-27','19:30','group'),
    (71,'2026-06-27','22:00','group'),(72,'2026-06-27','22:00','group'),
    (73,'2026-06-28','15:00','r32'), (74,'2026-06-29','16:30','r32'),
    (75,'2026-06-29','21:00','r32'), (76,'2026-06-29','13:00','r32'),
    (77,'2026-06-30','17:00','r32'), (78,'2026-06-30','13:00','r32'),
    (79,'2026-06-30','21:00','r32'), (80,'2026-07-01','12:00','r32'),
    (81,'2026-07-01','20:00','r32'), (82,'2026-07-01','16:00','r32'),
    (83,'2026-07-02','19:00','r32'), (84,'2026-07-02','15:00','r32'),
    (85,'2026-07-02','23:00','r32'), (86,'2026-07-03','18:00','r32'),
    (87,'2026-07-03','21:30','r32'), (88,'2026-07-03','14:00','r32'),
    (89,'2026-07-04','17:00','r16'), (90,'2026-07-04','13:00','r16'),
    (91,'2026-07-05','16:00','r16'), (92,'2026-07-05','20:00','r16'),
    (93,'2026-07-06','15:00','r16'), (94,'2026-07-06','20:00','r16'),
    (95,'2026-07-07','12:00','r16'), (96,'2026-07-07','16:00','r16'),
    (97,'2026-07-09','16:00','qf'),  (98,'2026-07-10','15:00','qf'),
    (99,'2026-07-11','17:00','qf'),  (100,'2026-07-11','21:00','qf'),
    (101,'2026-07-14','15:00','sf'), (102,'2026-07-15','15:00','sf'),
    (103,'2026-07-18','17:00','third'),
    (104,'2026-07-19','15:00','final'),
]

MATCH_STAGE = {mid: stage for mid, _, _, stage in _MATCH_META}

def _to_utc(date_str, time_str):
    h, m = map(int, time_str.split(':'))
    dt = datetime.strptime(date_str, '%Y-%m-%d').replace(hour=h, minute=m)
    return dt + timedelta(hours=4)  # EDT = UTC-4

MATCH_KICKOFF_UTC = {mid: _to_utc(d, t) for mid, d, t, _ in _MATCH_META}
_MATCH_STAGE      = {mid: stage for mid, _, _, stage in _MATCH_META}

# How long each stage can last (minutes after kickoff):
#   group:    45 + 45 + 15 HT + 10 stoppage*2 + 20 buffer = 145
#   knockout: 45 + 45 + 15 HT + 30 ET + 5 ET-HT + 15 pens + 20 buffer = 175
def _live_window(stage):
    return timedelta(minutes=145 if stage == 'group' else 175)

def _any_match_active():
    now = datetime.utcnow()
    # Clock-based: within the active window after kickoff
    if any(ko <= now <= ko + _live_window(_MATCH_STAGE.get(mid, 'group'))
           for mid, ko in MATCH_KICKOFF_UTC.items()):
        return True
    # DB-based: any match still marked LIVE in match_meta (not yet FINISHED)
    try:
        with db() as c:
            row = c.execute(
                "SELECT 1 FROM match_meta WHERE status IN ('LIVE','HT') LIMIT 1"
            ).fetchone()
            return row is not None
    except Exception:
        return False

def match_is_locked(match_id):
    ko = MATCH_KICKOFF_UTC.get(match_id)
    if ko is None:
        return False
    stage = _MATCH_STAGE.get(match_id, 'group')
    try:
        with db() as c:
            row = c.execute(
                'SELECT admin_unlocked FROM match_meta WHERE match_id=?', (match_id,)
            ).fetchone()
            is_admin_unlocked = bool(row['admin_unlocked']) if row else False
    except Exception:
        is_admin_unlocked = False

    # Knockout matches: locked until admin explicitly opens (teams confirmed)
    if stage != 'group' and not is_admin_unlocked:
        return True

    # Default: time-based lock (5 min before kickoff)
    return datetime.utcnow() >= ko - timedelta(minutes=5)

# ── Points system ─────────────────────────────────────────────────────────────
STAGE_PTS = {
    'group': (1, 3), 'r32': (3, 6), 'r16': (3, 6),
    'qf': (5, 7), 'sf': (7, 15), 'third': (7, 15), 'final': (10, 20),
}

def calc_pts(ph, pa, sh, sa, stage, total_preds, same_score_count):
    outcome_pts, exact_pts = STAGE_PTS.get(stage, (0, 0))
    if ph == sh and pa == sa:
        p = exact_pts
        threshold = max(1, total_preds * (0.15 if stage == 'group' else 0.12))
        if same_score_count < threshold:
            p += 5 if stage == 'group' else 10
        return p
    pred_sign = (ph > pa) - (ph < pa)
    actual_sign = (sh > sa) - (sh < sa)
    if pred_sign == actual_sign:
        return outcome_pts
    return 0

def calc_pts_gd(ph, pa, sh, sa, stage, total_preds, same_score_count):
    """Same as calc_pts but adds +2 when the predicted goal difference matches actual."""
    pts = calc_pts(ph, pa, sh, sa, stage, total_preds, same_score_count)
    if pts > 0 and (ph - pa) == (sh - sa):
        pts += 2
    return pts

# ── Database ──────────────────────────────────────────────────────────────────

@contextmanager
def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def _migrate_users_if_needed(conn):
    cols = {r['name']: dict(r) for r in conn.execute('PRAGMA table_info(users)').fetchall()}
    if not cols:
        return
    discord_col = cols.get('discord_id', {})
    if discord_col.get('notnull', 0):
        logging.info('DB migration: removing discord_id NOT NULL, adding google_id/nickname/provider')
        conn.executescript('''
            ALTER TABLE users RENAME TO _users_bak;
            CREATE TABLE users (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id  TEXT UNIQUE,
                google_id   TEXT UNIQUE,
                username    TEXT NOT NULL,
                global_name TEXT,
                avatar      TEXT,
                nickname    TEXT,
                provider    TEXT NOT NULL DEFAULT 'discord',
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO users (id, discord_id, username, global_name, avatar, created_at)
            SELECT id, discord_id, username, global_name, avatar, created_at FROM _users_bak;
            DROP TABLE _users_bak;
        ''')
    else:
        for col, defn in [('google_id','TEXT'), ('nickname','TEXT'), ('provider',"TEXT DEFAULT 'discord'")]:
            if col not in cols:
                try:
                    conn.execute(f'ALTER TABLE users ADD COLUMN {col} {defn}')
                    if col == 'provider':
                        conn.execute("UPDATE users SET provider='discord' WHERE provider IS NULL AND discord_id IS NOT NULL")
                    logging.info(f'DB migration: added users.{col}')
                except Exception as e:
                    logging.warning(f'DB migration skip {col}: {e}')

def init_db():
    with db() as conn:
        _migrate_users_if_needed(conn)
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id  TEXT UNIQUE,
                google_id   TEXT UNIQUE,
                username    TEXT NOT NULL,
                global_name TEXT,
                avatar      TEXT,
                nickname    TEXT,
                provider    TEXT NOT NULL DEFAULT 'discord',
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS predictions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                match_id    INTEGER NOT NULL,
                home_score  INTEGER NOT NULL,
                away_score  INTEGER NOT NULL,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE(user_id, match_id)
            );
            CREATE TABLE IF NOT EXISTS match_results (
                match_id      INTEGER PRIMARY KEY,
                score_home    INTEGER NOT NULL,
                score_away    INTEGER NOT NULL,
                result_locked INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS match_meta (
                match_id       INTEGER PRIMARY KEY,
                external_id    TEXT,
                status         TEXT NOT NULL DEFAULT 'UPCOMING',
                admin_unlocked INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS bracket_state (
                id           INTEGER PRIMARY KEY DEFAULT 1,
                status       TEXT NOT NULL DEFAULT 'pending',
                slots_json   TEXT,
                results_json TEXT,
                updated_at   TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS bracket_picks (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                picks_json TEXT NOT NULL,
                score      INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE(user_id)
            );
        ''')
        # Migrate existing match_meta rows that lack admin_unlocked
        try:
            conn.execute('ALTER TABLE match_meta ADD COLUMN admin_unlocked INTEGER NOT NULL DEFAULT 0')
            logging.info('DB migration: added match_meta.admin_unlocked')
        except Exception:
            pass  # column already exists
        conn.commit()

# ── football-data.org integration ────────────────────────────────────────────

# Map football-data.org team names → our internal names
_FD_NAME_MAP = {
    'Korea Republic':         'South Korea',
    'Czech Republic':         'Czechia',
    "Côte d'Ivoire":         'Ivory Coast',
    'Congo DR':               'DR Congo',
    'Turkey':                 'Türkiye',
    'Bosnia-Herzegovina':     'Bosnia and Herzegovina',
    'United States':          'USA',
}

def _norm(name):
    return _FD_NAME_MAP.get(name, name)

# Group-stage match teams (matches 1-72 only — knockouts resolved at runtime)
_TEAM_MATCHES = {
    1:('Mexico','South Africa'),       2:('South Korea','Czechia'),
    3:('Canada','Bosnia and Herzegovina'), 4:('USA','Paraguay'),
    5:('Qatar','Switzerland'),         6:('Brazil','Morocco'),
    7:('Haiti','Scotland'),            8:('Australia','Türkiye'),
    9:('Germany','Curaçao'),           10:('Netherlands','Japan'),
    11:('Ivory Coast','Ecuador'),      12:('Sweden','Tunisia'),
    13:('Spain','Cape Verde'),         14:('Belgium','Egypt'),
    15:('Saudi Arabia','Uruguay'),     16:('Iran','New Zealand'),
    17:('France','Senegal'),           18:('Iraq','Norway'),
    19:('Argentina','Algeria'),        20:('Austria','Jordan'),
    21:('Portugal','DR Congo'),        22:('England','Croatia'),
    23:('Ghana','Panama'),             24:('Uzbekistan','Colombia'),
    25:('Czechia','South Africa'),     26:('Switzerland','Bosnia and Herzegovina'),
    27:('Canada','Qatar'),             28:('Mexico','South Korea'),
    29:('USA','Australia'),            30:('Scotland','Morocco'),
    31:('Brazil','Haiti'),             32:('Türkiye','Paraguay'),
    33:('Netherlands','Sweden'),       34:('Germany','Ivory Coast'),
    35:('Ecuador','Curaçao'),          36:('Tunisia','Japan'),
    37:('Spain','Saudi Arabia'),       38:('Belgium','Iran'),
    39:('Uruguay','Cape Verde'),       40:('New Zealand','Egypt'),
    41:('Argentina','Austria'),        42:('France','Iraq'),
    43:('Norway','Senegal'),           44:('Jordan','Algeria'),
    45:('Portugal','Uzbekistan'),      46:('England','Ghana'),
    47:('Panama','Croatia'),           48:('Colombia','DR Congo'),
    49:('Switzerland','Canada'),       50:('Bosnia and Herzegovina','Qatar'),
    51:('Scotland','Brazil'),          52:('Morocco','Haiti'),
    53:('Czechia','Mexico'),           54:('South Africa','South Korea'),
    55:('Ecuador','Germany'),          56:('Curaçao','Ivory Coast'),
    57:('Tunisia','Netherlands'),      58:('Japan','Sweden'),
    59:('Türkiye','USA'),              60:('Paraguay','Australia'),
    61:('Norway','France'),            62:('Senegal','Iraq'),
    63:('Uruguay','Spain'),            64:('Cape Verde','Saudi Arabia'),
    65:('New Zealand','Belgium'),      66:('Egypt','Iran'),
    67:('Panama','England'),           68:('Croatia','Ghana'),
    69:('Colombia','Portugal'),        70:('DR Congo','Uzbekistan'),
    71:('Jordan','Argentina'),         72:('Algeria','Austria'),
}
_TEAM_TO_MATCH = {v: k for k, v in _TEAM_MATCHES.items()}

# UTC datetime prefix → match_id (for knockout rounds where teams are TBD)
_UTCDT_TO_MATCH = {
    _to_utc(d, t).strftime('%Y-%m-%dT%H:%M'): mid
    for mid, d, t, _ in _MATCH_META
    if mid > 72
}

# ── Group stage → bracket slot mapping ───────────────────────────────────────

# Which 6 match IDs belong to each group (MD1 + MD2 + MD3)
_GROUP_MATCHES = {
    'A': [1, 2, 25, 28, 53, 54],   'B': [9, 11, 34, 35, 55, 56],
    'C': [10, 12, 33, 36, 57, 58], 'D': [4, 8, 29, 32, 59, 60],
    'E': [17, 18, 42, 43, 61, 62], 'F': [13, 15, 37, 39, 63, 64],
    'G': [14, 16, 38, 40, 65, 66], 'H': [22, 23, 46, 47, 67, 68],
    'I': [21, 24, 45, 48, 69, 70], 'J': [19, 20, 41, 44, 71, 72],
    'K': [3, 5, 26, 27, 49, 50],   'L': [6, 7, 30, 31, 51, 52],
}

# Bracket slot pos → (group_letter, rank)  rank 1=winner, 2=runner-up
# Slots 4,10,14,16,18,20,26,30 are "best 3rd place" — not in this map
_SLOT_MAP = {
    1:('A',2), 2:('B',2), 3:('E',1), 5:('F',1), 6:('C',2),
    7:('C',1), 8:('F',2), 9:('I',1), 11:('E',2), 12:('I',2),
    13:('A',1), 15:('L',1), 17:('D',1), 19:('G',1),
    21:('K',2), 22:('L',2), 23:('H',1), 24:('J',2),
    25:('B',1), 27:('J',1), 28:('H',2), 29:('K',1),
    31:('D',2), 32:('G',2),
}

# R32 match ID → groups whose 3rd-place team may fill the best-3rd away slot
_R32_3RD_ELIGIBLE = {
    74: list('ABCDF'), 77: list('CDFGH'), 79: list('CEFHI'),
    80: list('EHIJK'), 81: list('BEFIJ'), 82: list('AEHIJ'),
    85: list('EFGIJ'), 87: list('DEIJL'),
}
# R32 match ID → the bracket slot position of that match's best-3rd slot (always away/even)
_R32_3RD_SLOT_POS = {74: 4, 77: 10, 79: 14, 80: 16, 81: 18, 82: 20, 85: 26, 87: 30}


def sync_scores(force=False):
    if not FOOTBALL_DATA_KEY:
        return {'synced': 0, 'live': 0, 'errors': [{'reason': 'FOOTBALL_DATA_KEY not configured'}]}
    if not force and not _any_match_active():
        return {'synced': 0, 'live': 0, 'skipped': 'no match in active window'}

    try:
        resp = req.get(
            'https://api.football-data.org/v4/competitions/WC/matches',
            headers={'X-Auth-Token': FOOTBALL_DATA_KEY},
            timeout=15,
        )
        if not resp.ok:
            logging.warning(f'football-data.org HTTP {resp.status_code}')
            return {'synced': 0, 'live': 0, 'errors': [{'reason': f'API {resp.status_code}'}]}
        matches = resp.json().get('matches', [])
    except Exception as e:
        logging.warning(f'football-data.org error: {e}')
        return {'synced': 0, 'live': 0, 'errors': [{'reason': str(e)}]}

    # Load existing api-id → internal match_id cache, and set of already-finished IDs
    with db() as c:
        meta_rows = c.execute('SELECT match_id, external_id, status FROM match_meta').fetchall()
    stored   = {r['external_id']: r['match_id'] for r in meta_rows if r['external_id']}
    done_ids = {r['match_id'] for r in meta_rows if r['status'] == 'FINISHED'}

    summary = {'synced': 0, 'live': 0, 'updated': [], 'errors': []}

    for m in matches:
        status = m.get('status', '')
        if status not in ('FINISHED', 'IN_PLAY', 'PAUSED', 'EXTRA_TIME', 'PENALTY_SHOOTOUT'):
            if status not in ('SCHEDULED', 'TIMED_OUT', 'TIMED'):
                home_n = (m.get('homeTeam') or m.get('home') or {}).get('name', '?')
                away_n = (m.get('awayTeam') or m.get('away') or {}).get('name', '?')
                logging.info(f'sync skip: {home_n} vs {away_n} status={status}')
            continue

        api_id = str(m.get('id', ''))

        # Resolve internal match_id
        internal_id = stored.get(api_id)
        if not internal_id:
            home = _norm((m.get('homeTeam') or m.get('home') or {}).get('name', ''))
            away = _norm((m.get('awayTeam') or m.get('away') or {}).get('name', ''))
            internal_id = _TEAM_TO_MATCH.get((home, away))
        if not internal_id:
            utc_prefix = (m.get('utcDate') or '')[:16]  # "2026-06-28T19:00"
            internal_id = _UTCDT_TO_MATCH.get(utc_prefix)
        if not internal_id:
            home = (m.get('homeTeam') or m.get('home') or {}).get('name', '?')
            away = (m.get('awayTeam') or m.get('away') or {}).get('name', '?')
            summary['errors'].append({'reason': f'unmatched: {home} vs {away} (fd#{api_id})'})
            continue

        # Skip matches already confirmed finished — no need to re-write
        if internal_id in done_ids:
            stored[api_id] = internal_id
            continue

        ft = (m.get('score') or {}).get('fullTime') or {}
        h, a = ft.get('home'), ft.get('away')
        if h is None or a is None:
            h, a = 0, 0  # match just started, score not yet populated

        # Verify home/away order matches our internal mapping and swap scores if inverted.
        # This fixes cases where the API lists teams in the opposite order and we resolved
        # the match via UTC datetime rather than team name pair.
        if internal_id in _TEAM_MATCHES:
            our_home, our_away = _TEAM_MATCHES[internal_id]
            api_home = _norm((m.get('homeTeam') or m.get('home') or {}).get('name', ''))
            api_away = _norm((m.get('awayTeam') or m.get('away') or {}).get('name', ''))
            if api_home and api_away and api_home != our_home:
                h, a = a, h
                logging.info(
                    f'match {internal_id}: API order {api_home}/{api_away} != ours {our_home}/{our_away} '
                    f'— scores swapped to {h}-{a}'
                )

        locked     = 1 if status == 'FINISHED' else 0
        db_status  = 'FINISHED' if status == 'FINISHED' else ('HT' if status == 'PAUSED' else 'LIVE')
        # Log all live match statuses to help diagnose API delays
        logging.info(f'sync processing: match {internal_id} api_status={status} score={h}-{a}')

        with db() as c:
            c.execute('''
                INSERT INTO match_results (match_id, score_home, score_away, result_locked)
                VALUES (?,?,?,?)
                ON CONFLICT(match_id) DO UPDATE SET
                    score_home    = excluded.score_home,
                    score_away    = excluded.score_away,
                    result_locked = excluded.result_locked
            ''', (internal_id, int(h), int(a), locked))
            c.execute('''
                INSERT INTO match_meta (match_id, external_id, status)
                VALUES (?,?,?)
                ON CONFLICT(match_id) DO UPDATE SET
                    external_id = excluded.external_id,
                    status      = excluded.status
            ''', (internal_id, api_id, db_status))
            c.commit()

        stored[api_id] = internal_id
        logging.info(f'Score sync match {internal_id}: {h}-{a} ({status})')
        if locked:
            summary['synced'] += 1
            summary['updated'].append({'match_id': internal_id, 'score': f'{h}-{a}'})
        else:
            summary['live'] += 1

    if summary['synced'] > 0:
        try:
            sync_bracket_slots()
        except Exception as e:
            logging.warning(f'bracket slot sync error: {e}')
    return summary

# ── Scheduler (started at module level so Passenger/gunicorn picks it up) ─────
_scheduler = BackgroundScheduler(daemon=True)
_FIRST_MATCH_UTC = min(MATCH_KICKOFF_UTC.values())
_scheduler.add_job(sync_scores, 'interval', minutes=2, id='sync_scores',
                   max_instances=1, coalesce=True, start_date=_FIRST_MATCH_UTC)

# ── Bracket slot auto-sync ───────────────────────────────────────────────────

def _compute_group_standings(results):
    """Compute standings for all 12 groups from {match_id: (home, away)} results."""
    teams = {}
    for grp, mids in _GROUP_MATCHES.items():
        teams[grp] = {}
        for mid in mids:
            for t in _TEAM_MATCHES[mid]:
                if t not in teams[grp]:
                    teams[grp][t] = dict(mp=0, w=0, d=0, l=0, gf=0, ga=0, gd=0, pts=0)
        for mid in mids:
            if mid not in results:
                continue
            h, a = results[mid]
            ht, at = _TEAM_MATCHES[mid]
            ts_h, ts_a = teams[grp][ht], teams[grp][at]
            ts_h['mp'] += 1; ts_a['mp'] += 1
            ts_h['gf'] += h; ts_h['ga'] += a; ts_h['gd'] = ts_h['gf'] - ts_h['ga']
            ts_a['gf'] += a; ts_a['ga'] += h; ts_a['gd'] = ts_a['gf'] - ts_a['ga']
            if h > a:
                ts_h['w'] += 1; ts_h['pts'] += 3; ts_a['l'] += 1
            elif h < a:
                ts_a['w'] += 1; ts_a['pts'] += 3; ts_h['l'] += 1
            else:
                ts_h['d'] += 1; ts_h['pts'] += 1; ts_a['d'] += 1; ts_a['pts'] += 1
    sorted_st = {}
    for grp, ts in teams.items():
        lst = [{'name': n, **s} for n, s in ts.items()]
        lst.sort(key=lambda t: (-t['pts'], -t['gd'], -t['gf'], t['name']))
        sorted_st[grp] = lst
    return sorted_st


def _is_position_clinched(standings, results, grp, pos):
    """True if position `pos` (0=1st, 1=2nd) is mathematically locked in `grp`."""
    teams = standings.get(grp, [])
    if len(teams) < 4:
        return False
    mids = _GROUP_MATCHES[grp]
    max_pts = {}
    for t in teams:
        played = sum(1 for mid in mids if mid in results and t['name'] in _TEAM_MATCHES[mid])
        max_pts[t['name']] = t['pts'] + 3 * (3 - played)

    def can_beat(ref, other):
        if max_pts[other['name']] < ref['pts']:
            return False
        if max_pts[other['name']] > ref['pts']:
            return True
        h2h_mid = next(
            (mid for mid in mids if set(_TEAM_MATCHES[mid]) == {ref['name'], other['name']}),
            None)
        if h2h_mid is None or h2h_mid not in results:
            return True
        h, a = results[h2h_mid]
        ref_home = _TEAM_MATCHES[h2h_mid][0] == ref['name']
        ref_g = h if ref_home else a
        other_g = a if ref_home else h
        return ref_g <= other_g

    first_clinched = all(not can_beat(teams[0], t) for t in teams[1:])
    if pos == 0:
        return first_clinched
    if pos == 1:
        return first_clinched and all(not can_beat(teams[1], t) for t in teams[2:])
    return False


def _assign_third_place_teams(qualifying_groups):
    """Bipartite matching: assign each of the 8 best 3rd-place groups to a R32 slot.
    Returns {r32_match_id: group_letter}."""
    sorted_g = sorted(qualifying_groups,
                      key=lambda g: sum(1 for el in _R32_3RD_ELIGIBLE.values() if g in el))
    res, used = {}, set()
    def bt(i):
        if i == len(sorted_g): return True
        g = sorted_g[i]
        for mid, eligible in sorted(_R32_3RD_ELIGIBLE.items()):
            if g in eligible and mid not in used:
                res[mid] = g; used.add(mid)
                if bt(i + 1): return True
                del res[mid]; used.discard(mid)
        return False
    bt(0)
    return res


def sync_bracket_slots():
    """Recompute bracket slot teams from finished group results and clinched standings.
    Safe to call at any time — no-ops if bracket is closed."""
    with db() as c:
        state = c.execute('SELECT slots_json, status FROM bracket_state WHERE id=1').fetchone()
        if state and state['status'] == 'closed':
            return {'skipped': 'bracket closed'}
        result_rows = c.execute(
            'SELECT match_id, score_home, score_away FROM match_results WHERE result_locked=1'
        ).fetchall()

    results = {r['match_id']: (r['score_home'], r['score_away']) for r in result_rows}
    standings = _compute_group_standings(results)

    slots = {p: 'TBD' for p in range(1, 33)}
    if state and state['slots_json']:
        for s in json.loads(state['slots_json']):
            slots[s['pos']] = s['team']

    updated = []

    # Fill group winner / runner-up slots
    for pos, (grp, rank) in _SLOT_MAP.items():
        idx = rank - 1
        grp_complete = all(mid in results for mid in _GROUP_MATCHES[grp])
        if grp_complete or _is_position_clinched(standings, results, grp, idx):
            team_list = standings.get(grp, [])
            new_team = team_list[idx]['name'] if idx < len(team_list) else 'TBD'
            if slots.get(pos) != new_team:
                slots[pos] = new_team
                updated.append({'pos': pos, 'team': new_team})

    # Fill best-3rd slots only once all 12 groups are done
    all_complete = all(all(mid in results for mid in mids) for mids in _GROUP_MATCHES.values())
    if all_complete:
        thirds = [{'group': g, **standings[g][2]}
                  for g in 'ABCDEFGHIJKL' if len(standings.get(g, [])) >= 3]
        thirds.sort(key=lambda t: (-t['pts'], -t['gd'], -t['gf'], t['name']))
        best8 = thirds[:8]
        slot_map = _assign_third_place_teams([t['group'] for t in best8])
        for mid, grp in slot_map.items():
            team = next((t for t in best8 if t['group'] == grp), None)
            if team:
                slot_pos = _R32_3RD_SLOT_POS[mid]
                if slots.get(slot_pos) != team['name']:
                    slots[slot_pos] = team['name']
                    updated.append({'pos': slot_pos, 'team': team['name']})

    if updated or state is None:
        slots_list = [{'pos': p, 'team': t} for p, t in sorted(slots.items())]
        with db() as c:
            c.execute('''
                INSERT INTO bracket_state (id, slots_json) VALUES (1, ?)
                ON CONFLICT(id) DO UPDATE SET slots_json=excluded.slots_json, updated_at=datetime('now')
            ''', (json.dumps(slots_list),))
            c.commit()
        if updated:
            logging.info(f'Bracket slots synced: {[u["team"] for u in updated]}')

    return {'updated': updated, 'all_groups_complete': all_complete}


# ── Static ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/terms')
def terms():
    return send_from_directory('static', 'terms.html')

@app.route('/bracket')
def bracket_page():
    return send_from_directory('static', 'bracket.html')

# ── Discord OAuth ─────────────────────────────────────────────────────────────

@app.route('/auth/discord')
def discord_auth():
    if not DISCORD_CLIENT_ID or not DISCORD_CLIENT_SECRET:
        return 'Discord OAuth not configured.', 500
    state = secrets.token_urlsafe(16)
    session['oauth_state'] = state
    params = {
        'client_id': DISCORD_CLIENT_ID,
        'redirect_uri': DISCORD_REDIRECT_URI,
        'response_type': 'code',
        'scope': 'identify',
        'state': state,
    }
    return redirect('https://discord.com/api/oauth2/authorize?' + urlencode(params))

@app.route('/auth/discord/callback')
def discord_callback():
    code  = request.args.get('code')
    state = request.args.get('state')
    if not code or state != session.pop('oauth_state', None):
        return redirect('/?auth_error=state')

    link_uid = session.pop('link_user_id', None)

    token_resp = req.post(
        'https://discord.com/api/oauth2/token',
        data={
            'client_id':     DISCORD_CLIENT_ID,
            'client_secret': DISCORD_CLIENT_SECRET,
            'grant_type':    'authorization_code',
            'code':          code,
            'redirect_uri':  DISCORD_REDIRECT_URI,
        },
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        timeout=10,
    )
    if not token_resp.ok:
        return redirect('/?auth_error=token')
    token = token_resp.json().get('access_token')

    user_resp = req.get(
        'https://discord.com/api/users/@me',
        headers={'Authorization': f'Bearer {token}'},
        timeout=10,
    )
    if not user_resp.ok:
        return redirect('/?auth_error=user')

    d = user_resp.json()
    discord_id  = d['id']
    username    = d['username']
    global_name = d.get('global_name') or username
    avatar_hash = d.get('avatar')
    avatar_url  = (f'https://cdn.discordapp.com/avatars/{discord_id}/{avatar_hash}.png'
                   if avatar_hash else None)

    if link_uid:
        with db() as c:
            existing = c.execute('SELECT id FROM users WHERE discord_id=?', (discord_id,)).fetchone()
            if existing and existing['id'] != link_uid:
                return redirect('/?auth_error=discord_taken')
            c.execute('''UPDATE users SET discord_id=?, username=?, global_name=?,
                         avatar=CASE WHEN avatar LIKE 'data:%' THEN avatar ELSE ? END
                         WHERE id=?''',
                      (discord_id, username, global_name, avatar_url, link_uid))
            c.commit()
        return redirect('/')

    with db() as c:
        c.execute('''
            INSERT INTO users (discord_id, username, global_name, avatar)
            VALUES (?,?,?,?)
            ON CONFLICT(discord_id) DO UPDATE SET
                username    = excluded.username,
                global_name = excluded.global_name,
                avatar      = CASE WHEN users.avatar LIKE 'data:%'
                              THEN users.avatar ELSE excluded.avatar END
        ''', (discord_id, username, global_name, avatar_url))
        c.commit()
        row = c.execute('SELECT id FROM users WHERE discord_id=?', (discord_id,)).fetchone()

    session.permanent = True
    session['user_id'] = row['id']
    return redirect('/')

@app.route('/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'ok': True})

@app.route('/auth/discord/link')
def discord_link():
    uid = session.get('user_id')
    if not uid:
        return redirect('/')
    if not DISCORD_CLIENT_ID or not DISCORD_CLIENT_SECRET:
        return 'Discord OAuth not configured.', 500
    state = secrets.token_urlsafe(16)
    session['oauth_state'] = state
    session['link_user_id'] = uid
    params = {
        'client_id': DISCORD_CLIENT_ID,
        'redirect_uri': DISCORD_REDIRECT_URI,
        'response_type': 'code',
        'scope': 'identify',
        'state': state,
        'prompt': 'consent',
    }
    return redirect('https://discord.com/api/oauth2/authorize?' + urlencode(params))

@app.route('/auth/google')
def google_auth():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return 'Google OAuth not configured.', 500
    state = secrets.token_urlsafe(16)
    session['oauth_state'] = state
    params = {
        'client_id':     GOOGLE_CLIENT_ID,
        'redirect_uri':  GOOGLE_REDIRECT_URI,
        'response_type': 'code',
        'scope':         'openid profile',
        'state':         state,
        'access_type':   'online',
        'prompt':        'select_account',
    }
    return redirect('https://accounts.google.com/o/oauth2/v2/auth?' + urlencode(params))

@app.route('/auth/google/link')
def google_link():
    uid = session.get('user_id')
    if not uid:
        return redirect('/')
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return 'Google OAuth not configured.', 500
    state = secrets.token_urlsafe(16)
    session['oauth_state'] = state
    session['link_user_id'] = uid
    params = {
        'client_id':     GOOGLE_CLIENT_ID,
        'redirect_uri':  GOOGLE_REDIRECT_URI,
        'response_type': 'code',
        'scope':         'openid profile',
        'state':         state,
        'prompt':        'select_account',
    }
    return redirect('https://accounts.google.com/o/oauth2/v2/auth?' + urlencode(params))

@app.route('/auth/google/callback')
def google_callback():
    code  = request.args.get('code')
    state = request.args.get('state')
    if not code or state != session.pop('oauth_state', None):
        return redirect('/?auth_error=state')

    link_uid = session.pop('link_user_id', None)

    token_resp = req.post(
        'https://oauth2.googleapis.com/token',
        data={
            'client_id':     GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'grant_type':    'authorization_code',
            'code':          code,
            'redirect_uri':  GOOGLE_REDIRECT_URI,
        },
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        timeout=10,
    )
    if not token_resp.ok:
        return redirect('/?auth_error=token')

    access_token = token_resp.json().get('access_token')
    user_resp = req.get(
        'https://www.googleapis.com/oauth2/v3/userinfo',
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=10,
    )
    if not user_resp.ok:
        return redirect('/?auth_error=user')

    d = user_resp.json()
    google_id  = d.get('sub')
    name       = d.get('name') or d.get('email', '').split('@')[0] or 'User'
    avatar_url = d.get('picture')

    if not google_id:
        return redirect('/?auth_error=user')

    if link_uid:
        with db() as c:
            existing = c.execute('SELECT id FROM users WHERE google_id=?', (google_id,)).fetchone()
            if existing and existing['id'] != link_uid:
                return redirect('/?auth_error=google_taken')
            c.execute('''UPDATE users SET google_id=?,
                         avatar=CASE WHEN avatar LIKE 'data:%' THEN avatar ELSE ? END
                         WHERE id=?''',
                      (google_id, avatar_url, link_uid))
            c.commit()
        return redirect('/')

    with db() as c:
        c.execute('''
            INSERT INTO users (google_id, username, global_name, avatar, provider)
            VALUES (?,?,?,?,'google')
            ON CONFLICT(google_id) DO UPDATE SET
                username    = excluded.username,
                global_name = excluded.global_name,
                avatar      = CASE WHEN users.avatar LIKE 'data:%'
                              THEN users.avatar ELSE excluded.avatar END
        ''', (google_id, name, name, avatar_url))
        c.commit()
        row = c.execute('SELECT id FROM users WHERE google_id=?', (google_id,)).fetchone()

    session.permanent = True
    session['user_id'] = row['id']
    return redirect('/')

# ── API ───────────────────────────────────────────────────────────────────────

@app.route('/api/me')
def me():
    uid = session.get('user_id')
    if not uid:
        return jsonify({'user': None})
    with db() as c:
        row = c.execute(
            'SELECT id, discord_id, google_id, username, global_name, avatar, nickname, provider FROM users WHERE id=?', (uid,)
        ).fetchone()
    if not row:
        session.clear()
        return jsonify({'user': None})
    u = dict(row)
    discord_id        = u.pop('discord_id')
    u['is_admin']     = (discord_id or '') in ADMIN_IDS
    u['has_discord']  = bool(discord_id)
    u['has_google']   = bool(u.pop('google_id'))
    u['provider']     = u['provider'] or 'discord'
    u['display_name'] = u['nickname'] or u['global_name'] or u['username']
    return jsonify({'user': u})

@app.route('/api/predictions')
def get_predictions():
    uid = session.get('user_id')
    if not uid:
        return jsonify({'predictions': {}})
    with db() as c:
        rows = c.execute(
            'SELECT match_id, home_score, away_score FROM predictions WHERE user_id=?', (uid,)
        ).fetchall()
    return jsonify({'predictions': {
        str(r['match_id']): {'home': r['home_score'], 'away': r['away_score']}
        for r in rows
    }})

@app.route('/api/predictions/<int:match_id>', methods=['POST'])
def save_prediction(match_id):
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': 'Not logged in'}), 401
    if not 1 <= match_id <= 104:
        return jsonify({'error': 'Invalid match'}), 400
    if match_is_locked(match_id):
        return jsonify({'error': 'Match has kicked off — predictions are locked'}), 403

    data = request.get_json(silent=True) or {}
    home = data.get('home')
    away = data.get('away')
    if not isinstance(home, int) or not isinstance(away, int):
        return jsonify({'error': 'Scores must be integers'}), 400
    if not (0 <= home <= 30 and 0 <= away <= 30):
        return jsonify({'error': 'Score out of range'}), 400

    with db() as c:
        c.execute('''
            INSERT INTO predictions (user_id, match_id, home_score, away_score)
            VALUES (?,?,?,?)
            ON CONFLICT(user_id, match_id) DO UPDATE SET
                home_score = excluded.home_score,
                away_score = excluded.away_score,
                updated_at = CURRENT_TIMESTAMP
        ''', (uid, match_id, home, away))
        c.commit()
    return jsonify({'ok': True})

@app.route('/api/predictions/<int:match_id>', methods=['DELETE'])
def delete_prediction(match_id):
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': 'Not logged in'}), 401
    if match_is_locked(match_id):
        return jsonify({'error': 'Match has kicked off — predictions are locked'}), 403
    with db() as c:
        c.execute('DELETE FROM predictions WHERE user_id=? AND match_id=?', (uid, match_id))
        c.commit()
    return jsonify({'ok': True})

@app.route('/api/results')
def get_results():
    with db() as c:
        rows = c.execute('''
            SELECT mr.match_id, mr.score_home, mr.score_away, mr.result_locked,
                   COALESCE(mm.status, CASE WHEN mr.result_locked=1 THEN 'FINISHED' ELSE 'LIVE' END) AS status,
                   COALESCE(mm.admin_unlocked, 0) AS admin_unlocked
            FROM match_results mr
            LEFT JOIN match_meta mm ON mm.match_id = mr.match_id
        ''').fetchall()
        unlocked_rows = c.execute(
            'SELECT match_id FROM match_meta WHERE admin_unlocked=1'
        ).fetchall()
    result_map = {
        str(r['match_id']): {
            'home': r['score_home'],
            'away': r['score_away'],
            'locked': bool(r['result_locked']),
            'status': r['status'],
            'admin_unlocked': bool(r['admin_unlocked']),
        }
        for r in rows
    }
    # Send unlocked match IDs separately so matches without a score entry
    # don't get a fake result object that corrupts the score display.
    admin_unlocked_ids = [r['match_id'] for r in unlocked_rows]
    return jsonify({'results': result_map, 'admin_unlocked': admin_unlocked_ids})

@app.route('/api/leaderboard')
def leaderboard():
    with db() as c:
        result_rows = c.execute(
            'SELECT match_id, score_home, score_away FROM match_results WHERE result_locked=1'
        ).fetchall()
        result_map = {r['match_id']: (r['score_home'], r['score_away']) for r in result_rows}

        rarity = {}
        for mid, (sh, sa) in result_map.items():
            total = c.execute('SELECT COUNT(*) FROM predictions WHERE match_id=?', (mid,)).fetchone()[0]
            same  = c.execute(
                'SELECT COUNT(*) FROM predictions WHERE match_id=? AND home_score=? AND away_score=?',
                (mid, sh, sa)).fetchone()[0]
            rarity[mid] = (total, same)

        users = c.execute('SELECT id, username, global_name, avatar, nickname FROM users').fetchall()
        board = []
        for user in users:
            pred_rows = c.execute(
                'SELECT match_id, home_score, away_score FROM predictions WHERE user_id=?',
                (user['id'],)).fetchall()
            preds = {r['match_id']: (r['home_score'], r['away_score']) for r in pred_rows}
            pts = 0
            bonus = 0
            exact = 0
            good = 0
            for mid, (sh, sa) in result_map.items():
                if mid not in preds:
                    continue
                ph, pa = preds[mid]
                total_p, same_p = rarity[mid]
                if ph == sh and pa == sa:
                    exact += 1
                    if same_p < max(1, total_p * (0.15 if MATCH_STAGE[mid] == 'group' else 0.12)):
                        bonus += 1
                else:
                    pred_sign = (ph > pa) - (ph < pa)
                    actual_sign = (sh > sa) - (sh < sa)
                    if pred_sign == actual_sign:
                        good += 1
                pts += calc_pts(ph, pa, sh, sa, MATCH_STAGE[mid], total_p, same_p)
            board.append({
                'user_id': user['id'],
                'name': user['nickname'] or user['global_name'] or user['username'],
                'avatar': user['avatar'],
                'points': pts,
                'predictions': len(preds),
                'bonus': bonus,
                'exact': exact,
                'good': good,
            })

    board.sort(key=lambda x: (-x['points'], -x['exact'], -x['good'], -x['bonus'], x['name'].lower(), x['user_id']))
    return jsonify({'leaderboard': board, 'scored_matches': len(result_map)})

@app.route('/api/leaderboard/alt')
def leaderboard_alt():
    _, err = _require_admin()
    if err:
        return err
    with db() as c:
        result_rows = c.execute(
            'SELECT match_id, score_home, score_away FROM match_results WHERE result_locked=1'
        ).fetchall()
        result_map = {r['match_id']: (r['score_home'], r['score_away']) for r in result_rows}

        rarity = {}
        for mid, (sh, sa) in result_map.items():
            total = c.execute('SELECT COUNT(*) FROM predictions WHERE match_id=?', (mid,)).fetchone()[0]
            same  = c.execute(
                'SELECT COUNT(*) FROM predictions WHERE match_id=? AND home_score=? AND away_score=?',
                (mid, sh, sa)).fetchone()[0]
            rarity[mid] = (total, same)

        users = c.execute('SELECT id, username, global_name, avatar, nickname FROM users').fetchall()
        board = []
        for user in users:
            pred_rows = c.execute(
                'SELECT match_id, home_score, away_score FROM predictions WHERE user_id=?',
                (user['id'],)).fetchall()
            preds = {r['match_id']: (r['home_score'], r['away_score']) for r in pred_rows}
            pts = 0
            bonus = 0
            exact = 0
            good = 0
            gd_bonus = 0
            for mid, (sh, sa) in result_map.items():
                if mid not in preds:
                    continue
                ph, pa = preds[mid]
                total_p, same_p = rarity[mid]
                base = calc_pts(ph, pa, sh, sa, MATCH_STAGE[mid], total_p, same_p)
                gd_extra = 2 if base > 0 and (ph - pa) == (sh - sa) else 0
                pts += base + gd_extra
                if gd_extra:
                    gd_bonus += 1
                if ph == sh and pa == sa:
                    exact += 1
                    if same_p < max(1, total_p * (0.15 if MATCH_STAGE[mid] == 'group' else 0.12)):
                        bonus += 1
                else:
                    pred_sign = (ph > pa) - (ph < pa)
                    actual_sign = (sh > sa) - (sh < sa)
                    if pred_sign == actual_sign:
                        good += 1
            board.append({
                'user_id': user['id'],
                'name': user['nickname'] or user['global_name'] or user['username'],
                'avatar': user['avatar'],
                'points': pts,
                'predictions': len(preds),
                'bonus': bonus,
                'exact': exact,
                'good': good,
                'gd_bonus': gd_bonus,
            })

    board.sort(key=lambda x: (-x['points'], -x['gd_bonus'], -x['exact'], -x['good'], -x['bonus'], x['name'].lower(), x['user_id']))
    return jsonify({'leaderboard': board, 'scored_matches': len(result_map)})

@app.route('/api/users/<int:user_id>/profile')
def user_profile(user_id):
    with db() as c:
        user = c.execute(
            'SELECT id, username, global_name, avatar, nickname FROM users WHERE id=?',
            (user_id,)).fetchone()
        if not user:
            return jsonify({'error': 'Not found'}), 404

        result_rows = c.execute(
            'SELECT match_id, score_home, score_away FROM match_results WHERE result_locked=1'
        ).fetchall()
        result_map = {r['match_id']: (r['score_home'], r['score_away']) for r in result_rows}

        pred_rows = c.execute(
            'SELECT match_id, home_score, away_score FROM predictions WHERE user_id=?',
            (user_id,)).fetchall()
        preds = {r['match_id']: (r['home_score'], r['away_score']) for r in pred_rows}

        rarity = {}
        for mid in result_map:
            sh, sa = result_map[mid]
            total = c.execute('SELECT COUNT(*) FROM predictions WHERE match_id=?', (mid,)).fetchone()[0]
            same  = c.execute(
                'SELECT COUNT(*) FROM predictions WHERE match_id=? AND home_score=? AND away_score=?',
                (mid, sh, sa)).fetchone()[0]
            rarity[mid] = (total, same)

        predictions = []
        for mid, (sh, sa) in result_map.items():
            if mid not in preds:
                continue
            ph, pa = preds[mid]
            total_p, same_p = rarity.get(mid, (0, 0))
            p = calc_pts(ph, pa, sh, sa, MATCH_STAGE[mid], total_p, same_p)
            predictions.append({
                'match_id': mid,
                'home_score': ph,
                'away_score': pa,
                'result_home': sh,
                'result_away': sa,
                'points': p,
                'stage': MATCH_STAGE[mid],
            })

        predictions.sort(key=lambda x: x['match_id'])
        pts_total = sum(p['points'] for p in predictions)
        def sign(x): return (x > 0) - (x < 0)
        exact = sum(1 for p in predictions if p['home_score']==p['result_home'] and p['away_score']==p['result_away'])
        good  = sum(1 for p in predictions
                    if not (p['home_score']==p['result_home'] and p['away_score']==p['result_away'])
                    and sign(p['home_score']-p['away_score']) == sign(p['result_home']-p['result_away']))

        return jsonify({
            'user': {
                'id': user['id'],
                'name': user['nickname'] or user['global_name'] or user['username'],
                'avatar': user['avatar'],
            },
            'stats': {
                'points': pts_total,
                'predictions': len(preds),
                'exact': exact,
                'good': good,
            },
            'predictions': predictions,
        })

@app.route('/api/matches/<int:match_id>/predictions')
def match_all_predictions(match_id):
    if not 1 <= match_id <= 104:
        return jsonify({'error': 'Invalid match'}), 400
    if not match_is_locked(match_id):
        return jsonify({'predictions': [], 'locked': False})
    with db() as c:
        rows = c.execute('''
            SELECT u.id, u.global_name, u.username, u.avatar, u.nickname,
                   p.home_score, p.away_score
            FROM predictions p
            JOIN users u ON u.id = p.user_id
            WHERE p.match_id = ?
            ORDER BY COALESCE(u.nickname, u.global_name, u.username) COLLATE NOCASE
        ''', (match_id,)).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d['display_name'] = r['nickname'] or r['global_name'] or r['username']
        result.append(d)
    return jsonify({'predictions': result, 'locked': True})

@app.route('/api/admin/restore-db', methods=['POST'])
def restore_db():
    token = request.headers.get('X-Restore-Token', '')
    if not RESTORE_SECRET or token != RESTORE_SECRET:
        return jsonify({'error': 'Forbidden'}), 403
    f = request.files.get('db')
    if not f:
        return jsonify({'error': 'No file uploaded'}), 400
    tmp = DB + '.upload'
    f.save(tmp)
    try:
        c = sqlite3.connect(tmp)
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        c.close()
        if not {'users', 'predictions'}.issubset(tables):
            raise ValueError('Missing required tables (users, predictions)')
    except Exception as e:
        try: os.unlink(tmp)
        except: pass
        return jsonify({'error': str(e)}), 400
    for ext in ('-wal', '-shm'):
        try: os.unlink(DB + ext)
        except FileNotFoundError: pass
    os.replace(tmp, DB)
    return jsonify({'ok': True, 'message': 'Database restored'})

@app.route('/api/admin/backup-db')
def backup_db():
    _, err = _require_admin()
    if err:
        return err
    if not os.path.exists(DB):
        return jsonify({'error': 'Database not found'}), 404
    return send_file(DB, as_attachment=True, download_name='wc2026_backup.db',
                     mimetype='application/x-sqlite3')

@app.route('/api/me/profile', methods=['POST'])
def update_profile():
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.get_json(silent=True) or {}
    updates = {}

    if 'nickname' in data:
        nick = (data['nickname'] or '').strip()[:30]
        updates['nickname'] = nick or None

    if 'avatar' in data:
        av = data['avatar']
        if av and not av.startswith('data:image/'):
            return jsonify({'error': 'Invalid image format'}), 400
        if av and len(av) > 200_000:
            return jsonify({'error': 'Image too large (max ~150 KB)'}), 400
        updates['avatar'] = av or None

    if updates:
        set_clause = ', '.join(f'{k}=?' for k in updates)
        with db() as c:
            c.execute(f'UPDATE users SET {set_clause} WHERE id=?',
                     [*updates.values(), uid])
            c.commit()

    return jsonify({'ok': True})

# ── Admin: match results ──────────────────────────────────────────────────────

@app.route('/api/admin/results/<int:match_id>', methods=['POST'])
def set_result(match_id):
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': 'Not logged in'}), 401
    if not 1 <= match_id <= 104:
        return jsonify({'error': 'Invalid match'}), 400
    with db() as c:
        user = c.execute('SELECT discord_id FROM users WHERE id=?', (uid,)).fetchone()
    if not user or user['discord_id'] not in ADMIN_IDS:
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json(silent=True) or {}
    home = data.get('home')
    away = data.get('away')
    status = data.get('status', 'FINISHED')
    if status not in ('LIVE', 'HT', 'FINISHED'):
        status = 'FINISHED'
    if not isinstance(home, int) or not isinstance(away, int):
        return jsonify({'error': 'Scores must be integers'}), 400
    if not (0 <= home <= 30 and 0 <= away <= 30):
        return jsonify({'error': 'Score out of range'}), 400

    locked    = 1 if status == 'FINISHED' else 0
    db_status = status
    with db() as c:
        c.execute('''
            INSERT INTO match_results (match_id, score_home, score_away, result_locked)
            VALUES (?,?,?,?)
            ON CONFLICT(match_id) DO UPDATE SET
                score_home    = excluded.score_home,
                score_away    = excluded.score_away,
                result_locked = excluded.result_locked
        ''', (match_id, home, away, locked))
        c.execute('''
            INSERT INTO match_meta (match_id, status)
            VALUES (?,?)
            ON CONFLICT(match_id) DO UPDATE SET status = excluded.status
        ''', (match_id, db_status))
        c.commit()
    if match_id <= 72 and locked:
        try:
            sync_bracket_slots()
        except Exception as e:
            logging.warning(f'bracket slot sync error: {e}')
    return jsonify({'ok': True})

@app.route('/api/admin/results/<int:match_id>', methods=['DELETE'])
def delete_result(match_id):
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': 'Not logged in'}), 401
    with db() as c:
        user = c.execute('SELECT discord_id FROM users WHERE id=?', (uid,)).fetchone()
    if not user or user['discord_id'] not in ADMIN_IDS:
        return jsonify({'error': 'Forbidden'}), 403
    with db() as c:
        c.execute('DELETE FROM match_results WHERE match_id=?', (match_id,))
        c.commit()
    return jsonify({'ok': True})

@app.route('/api/admin/matches/<int:match_id>/unlock', methods=['POST'])
def admin_unlock_match(match_id):
    _, err = _require_admin()
    if err:
        return err
    if not 1 <= match_id <= 104:
        return jsonify({'error': 'Invalid match'}), 400
    data = request.get_json(silent=True) or {}
    unlocked = bool(data.get('unlocked', True))
    with db() as c:
        c.execute('''
            INSERT INTO match_meta (match_id, status, admin_unlocked)
            VALUES (?, 'UPCOMING', ?)
            ON CONFLICT(match_id) DO UPDATE SET admin_unlocked = excluded.admin_unlocked
        ''', (match_id, 1 if unlocked else 0))
        c.commit()
    logging.info(f'Admin {"unlocked" if unlocked else "relocked"} match {match_id}')
    return jsonify({'ok': True, 'admin_unlocked': unlocked})

# ── Admin: sync ───────────────────────────────────────────────────────────────

def _require_admin():
    uid = session.get('user_id')
    if not uid:
        return None, (jsonify({'error': 'Not logged in'}), 401)
    with db() as c:
        user = c.execute('SELECT discord_id FROM users WHERE id=?', (uid,)).fetchone()
    if not user or user['discord_id'] not in ADMIN_IDS:
        return None, (jsonify({'error': 'Forbidden'}), 403)
    return user['discord_id'], None

@app.route('/api/admin/sync', methods=['POST'])
def admin_sync():
    _, err = _require_admin()
    if err:
        return err
    body  = request.get_json(silent=True) or {}
    force = bool(body.get('force', False))
    return jsonify(sync_scores(force=force))

@app.route('/api/cron/sync-scores')
def cron_sync():
    if CRON_SECRET and request.args.get('secret') != CRON_SECRET:
        return jsonify({'error': 'Unauthorized'}), 401
    return jsonify(sync_scores())

# ── Bracket Challenge ─────────────────────────────────────────────────────────
#
# Structure: 32 teams in slots 1-32 (sorted by bracket position).
# R32:  match i uses slots[i*2] vs slots[i*2+1], producing 16 winners → r32[0..15]
# R16:  match i uses r32[i*2] vs r32[i*2+1], producing 8 winners → r16[0..7]
# QF:   match i uses r16[i*2] vs r16[i*2+1], producing 4 winners → qf[0..3]
# SF:   match 0 uses qf[0] vs qf[1] → sf[0]; match 1 uses qf[2] vs qf[3] → sf[1]
# 3rd:  between the two SF losers (one from each SF match)
# Final: sf[0] vs sf[1]

BRACKET_PTS = {'r32': 10, 'r16': 20, 'qf': 40, 'sf': 80, 'final': 160, 'third': 40}


def _bracket_state(conn):
    return conn.execute('SELECT * FROM bracket_state WHERE id=1').fetchone()


def _calc_bracket_score(picks, results):
    pts = 0
    for rnd in ('r32', 'r16', 'qf', 'sf'):
        ppick = BRACKET_PTS[rnd]
        real = results.get(rnd) or []
        user = picks.get(rnd) or []
        for i, real_team in enumerate(real):
            if real_team and i < len(user) and user[i] == real_team:
                pts += ppick
    if results.get('final') and picks.get('final') == results['final']:
        pts += BRACKET_PTS['final']
    if results.get('third') and picks.get('third') == results['third']:
        pts += BRACKET_PTS['third']
    return pts


def _validate_bracket_picks(picks, slots_data):
    """Returns an error string, or None if picks are valid."""
    teams = [s['team'] for s in sorted(slots_data, key=lambda x: x['pos'])]

    r32   = picks.get('r32') or []
    r16   = picks.get('r16') or []
    qf    = picks.get('qf') or []
    sf    = picks.get('sf') or []
    final = picks.get('final')
    third = picks.get('third')

    if len(r32) != 16: return 'r32 must have exactly 16 picks'
    if len(r16) != 8:  return 'r16 must have exactly 8 picks'
    if len(qf)  != 4:  return 'qf must have exactly 4 picks'
    if len(sf)  != 2:  return 'sf must have exactly 2 picks'
    if not final:      return 'final pick is required'
    if not third:      return 'third place pick is required'

    for i in range(16):
        t1, t2 = teams[i * 2], teams[i * 2 + 1]
        if r32[i] not in (t1, t2):
            return f'r32[{i}]: "{r32[i]}" must be "{t1}" or "{t2}"'

    for i in range(8):
        t1, t2 = r32[i * 2], r32[i * 2 + 1]
        if r16[i] not in (t1, t2):
            return f'r16[{i}]: "{r16[i]}" must be "{t1}" or "{t2}"'

    for i in range(4):
        t1, t2 = r16[i * 2], r16[i * 2 + 1]
        if qf[i] not in (t1, t2):
            return f'qf[{i}]: "{qf[i]}" must be "{t1}" or "{t2}"'

    t1, t2 = qf[0], qf[1]
    if sf[0] not in (t1, t2):
        return f'sf[0]: "{sf[0]}" must be "{t1}" or "{t2}"'
    t1, t2 = qf[2], qf[3]
    if sf[1] not in (t1, t2):
        return f'sf[1]: "{sf[1]}" must be "{t1}" or "{t2}"'

    if final not in (sf[0], sf[1]):
        return f'final "{final}" must be one of the two SF winners'

    # 3rd place is between the two SF losers (one from each match)
    sf_loser_1 = qf[0] if sf[0] == qf[1] else qf[1]
    sf_loser_2 = qf[2] if sf[1] == qf[3] else qf[3]
    if third not in (sf_loser_1, sf_loser_2):
        return f'third "{third}" must be one of the SF losers: "{sf_loser_1}" or "{sf_loser_2}"'

    return None


@app.route('/api/bracket')
def get_bracket():
    uid = session.get('user_id')
    with db() as c:
        state    = _bracket_state(c)
        my_picks = None
        if uid:
            row = c.execute(
                'SELECT picks_json, score FROM bracket_picks WHERE user_id=?', (uid,)
            ).fetchone()
            if row:
                my_picks = {'picks': json.loads(row['picks_json']), 'score': row['score']}

    if not state:
        return jsonify({'status': 'pending', 'slots': None, 'results': None, 'my_picks': None})

    slots   = json.loads(state['slots_json'])   if state['slots_json']   else None
    results = json.loads(state['results_json']) if state['results_json'] else None

    return jsonify({
        'status':   state['status'],
        'slots':    slots,
        'results':  results,
        'my_picks': my_picks,
    })


@app.route('/api/bracket/picks', methods=['POST'])
def save_bracket_picks():
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': 'Not logged in'}), 401

    with db() as c:
        state = _bracket_state(c)

    if not state or state['status'] != 'open':
        return jsonify({'error': 'Bracket is not open for predictions'}), 403

    slots_data = json.loads(state['slots_json']) if state['slots_json'] else []
    if len(slots_data) != 32:
        return jsonify({'error': 'Bracket slots not fully configured yet'}), 503

    data  = request.get_json(silent=True) or {}
    picks = data.get('picks', {})

    err = _validate_bracket_picks(picks, slots_data)
    if err:
        return jsonify({'error': err}), 400

    results = json.loads(state['results_json']) if state['results_json'] else {}
    score   = _calc_bracket_score(picks, results)

    with db() as c:
        c.execute('''
            INSERT INTO bracket_picks (user_id, picks_json, score) VALUES (?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET
                picks_json = excluded.picks_json,
                score      = excluded.score,
                updated_at = datetime('now')
        ''', (uid, json.dumps(picks), score))
        c.commit()

    return jsonify({'ok': True, 'score': score})


@app.route('/api/bracket/leaderboard')
def bracket_leaderboard():
    with db() as c:
        state = _bracket_state(c)
        rows  = c.execute('''
            SELECT bp.user_id, bp.picks_json, bp.score, bp.updated_at,
                   u.username, u.global_name, u.avatar, u.nickname
            FROM bracket_picks bp
            JOIN users u ON u.id = bp.user_id
        ''').fetchall()

    results = {}
    if state and state['results_json']:
        results = json.loads(state['results_json'])

    board = []
    for row in rows:
        picks = json.loads(row['picks_json'])
        score = _calc_bracket_score(picks, results)
        board.append({
            'user_id':    row['user_id'],
            'name':       row['nickname'] or row['global_name'] or row['username'],
            'avatar':     row['avatar'],
            'score':      score,
            'updated_at': row['updated_at'],
        })

    board.sort(key=lambda x: (-x['score'], x['name'].lower()))
    return jsonify({'leaderboard': board, 'bracket_status': state['status'] if state else 'pending'})


@app.route('/api/bracket/picks/<int:user_id>')
def get_user_bracket(user_id):
    with db() as c:
        state = _bracket_state(c)
        user  = c.execute(
            'SELECT id, username, global_name, avatar, nickname FROM users WHERE id=?', (user_id,)
        ).fetchone()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        row = c.execute(
            'SELECT picks_json, score FROM bracket_picks WHERE user_id=?', (user_id,)
        ).fetchone()

    if not state or state['status'] == 'pending':
        return jsonify({'error': 'Bracket not available yet'}), 403
    if state['status'] == 'open':
        return jsonify({'error': 'Picks are hidden until the bracket closes'}), 403

    results = json.loads(state['results_json']) if state['results_json'] else {}
    picks   = json.loads(row['picks_json']) if row else None
    score   = _calc_bracket_score(picks, results) if picks else 0

    return jsonify({
        'user':  {
            'id':     user['id'],
            'name':   user['nickname'] or user['global_name'] or user['username'],
            'avatar': user['avatar'],
        },
        'picks': picks,
        'score': score,
    })


# ── Admin: bracket management ─────────────────────────────────────────────────

@app.route('/api/admin/bracket/status', methods=['POST'])
def admin_bracket_status():
    _, err = _require_admin()
    if err:
        return err
    data   = request.get_json(silent=True) or {}
    status = data.get('status')
    if status not in ('pending', 'open', 'closed'):
        return jsonify({'error': 'status must be pending, open, or closed'}), 400
    with db() as c:
        c.execute('''
            INSERT INTO bracket_state (id, status) VALUES (1, ?)
            ON CONFLICT(id) DO UPDATE SET status=excluded.status, updated_at=datetime('now')
        ''', (status,))
        c.commit()
    logging.info(f'Bracket status set to {status}')
    return jsonify({'ok': True, 'status': status})


@app.route('/api/admin/bracket/slots', methods=['POST'])
def admin_bracket_slots():
    _, err = _require_admin()
    if err:
        return err
    data  = request.get_json(silent=True) or {}
    slots = data.get('slots', [])
    if len(slots) != 32:
        return jsonify({'error': '32 slots required'}), 400
    positions = set()
    for s in slots:
        if not isinstance(s.get('team'), str) or not s['team'].strip():
            return jsonify({'error': 'Each slot needs a non-empty team name'}), 400
        pos = s.get('pos')
        if not isinstance(pos, int) or not 1 <= pos <= 32:
            return jsonify({'error': 'pos must be an integer 1-32'}), 400
        if pos in positions:
            return jsonify({'error': f'Duplicate pos {pos}'}), 400
        positions.add(pos)
    slots_str = json.dumps(sorted(slots, key=lambda x: x['pos']))
    with db() as c:
        c.execute('''
            INSERT INTO bracket_state (id, slots_json) VALUES (1, ?)
            ON CONFLICT(id) DO UPDATE SET slots_json=excluded.slots_json, updated_at=datetime('now')
        ''', (slots_str,))
        c.commit()
    return jsonify({'ok': True})


@app.route('/api/admin/bracket/results', methods=['POST'])
def admin_bracket_results():
    _, err = _require_admin()
    if err:
        return err
    data    = request.get_json(silent=True) or {}
    results = data.get('results', {})
    for rnd, n in (('r32', 16), ('r16', 8), ('qf', 4), ('sf', 2)):
        if rnd in results and results[rnd] is not None:
            if not isinstance(results[rnd], list) or len(results[rnd]) != n:
                return jsonify({'error': f'{rnd} must be a list of {n} entries (use null for unknown)'}), 400
    results_str = json.dumps(results)
    with db() as c:
        c.execute('''
            INSERT INTO bracket_state (id, results_json) VALUES (1, ?)
            ON CONFLICT(id) DO UPDATE SET results_json=excluded.results_json, updated_at=datetime('now')
        ''', (results_str,))
        picks_rows = c.execute('SELECT user_id, picks_json FROM bracket_picks').fetchall()
        for row in picks_rows:
            score = _calc_bracket_score(json.loads(row['picks_json']), results)
            c.execute('UPDATE bracket_picks SET score=? WHERE user_id=?', (score, row['user_id']))
        c.commit()
    return jsonify({'ok': True, 'scores_updated': len(picks_rows)})


@app.route('/api/admin/bracket/sync-slots', methods=['POST'])
def admin_sync_bracket_slots():
    _, err = _require_admin()
    if err:
        return err
    result = sync_bracket_slots()
    return jsonify({'ok': True, **(result or {})})


# ── Startup (runs on import — required for Passenger/gunicorn) ────────────────
init_db()
try:
    sync_bracket_slots()
except Exception as e:
    logging.warning(f'Initial bracket slot sync failed: {e}')
if FOOTBALL_DATA_KEY:
    _scheduler.start()
    atexit.register(lambda: _scheduler.shutdown(wait=False))
    logging.info('Score sync scheduler started (football-data.org, 2-min interval)')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8026, debug=False)
