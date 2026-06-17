import os
import secrets
import requests as req
from urllib.parse import urlencode
from flask import Flask, request, jsonify, session, send_from_directory, send_file, redirect
from flask_bcrypt import Bcrypt
import sqlite3
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
    (29,'2026-06-19','15:00','group'),(30,'2026-06-19','15:00','group'),
    (31,'2026-06-19','21:00','group'),(32,'2026-06-19','00:00','group'),
    (33,'2026-06-20','13:00','group'),(34,'2026-06-20','16:00','group'),
    (35,'2026-06-20','20:00','group'),(36,'2026-06-20','00:00','group'),
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

# ── Database ──────────────────────────────────────────────────────────────────

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    return conn

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
    conn = db()
    try:
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
        ''')
        # Migrate existing match_meta rows that lack admin_unlocked
        try:
            conn.execute('ALTER TABLE match_meta ADD COLUMN admin_unlocked INTEGER NOT NULL DEFAULT 0')
            logging.info('DB migration: added match_meta.admin_unlocked')
        except Exception:
            pass  # column already exists
        conn.commit()
    finally:
        conn.close()

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
    11:('Ivory Coast','Ecuador'),      12:('Tunisia','Sweden'),
    13:('Spain','Cape Verde'),         14:('Belgium','Egypt'),
    15:('Saudi Arabia','Uruguay'),     16:('Iran','New Zealand'),
    17:('France','Senegal'),           18:('Norway','Iraq'),
    19:('Argentina','Algeria'),        20:('Austria','Jordan'),
    21:('Portugal','DR Congo'),        22:('England','Croatia'),
    23:('Ghana','Panama'),             24:('Uzbekistan','Colombia'),
    25:('South Africa','Czechia'),     26:('Switzerland','Bosnia and Herzegovina'),
    27:('Canada','Qatar'),             28:('Mexico','South Korea'),
    29:('USA','Australia'),            30:('Scotland','Morocco'),
    31:('Brazil','Haiti'),             32:('Paraguay','Türkiye'),
    33:('Netherlands','Sweden'),       34:('Germany','Ivory Coast'),
    35:('Ecuador','Curaçao'),          36:('Tunisia','Japan'),
    37:('Spain','Saudi Arabia'),       38:('Belgium','Iran'),
    39:('Uruguay','Cape Verde'),       40:('New Zealand','Egypt'),
    41:('Argentina','Austria'),        42:('France','Iraq'),
    43:('Norway','Senegal'),           44:('Jordan','Algeria'),
    45:('Portugal','Uzbekistan'),      46:('England','Ghana'),
    47:('Panama','Croatia'),           48:('Colombia','DR Congo'),
    49:('Canada','Switzerland'),       50:('Qatar','Bosnia and Herzegovina'),
    51:('Scotland','Brazil'),          52:('Morocco','Haiti'),
    53:('Mexico','Czechia'),           54:('South Korea','South Africa'),
    55:('Ecuador','Germany'),          56:('Curaçao','Ivory Coast'),
    57:('Tunisia','Netherlands'),      58:('Japan','Sweden'),
    59:('USA','Türkiye'),              60:('Paraguay','Australia'),
    61:('Norway','France'),            62:('Senegal','Iraq'),
    63:('Uruguay','Spain'),            64:('Cape Verde','Saudi Arabia'),
    65:('New Zealand','Belgium'),      66:('Egypt','Iran'),
    67:('Panama','England'),           68:('Croatia','Ghana'),
    69:('Colombia','Portugal'),        70:('Uzbekistan','DR Congo'),
    71:('Jordan','Argentina'),         72:('Algeria','Austria'),
}
_TEAM_TO_MATCH = {v: k for k, v in _TEAM_MATCHES.items()}

# UTC datetime prefix → match_id (for knockout rounds where teams are TBD)
_UTCDT_TO_MATCH = {
    _to_utc(d, t).strftime('%Y-%m-%dT%H:%M'): mid
    for mid, d, t, _ in _MATCH_META
    if mid > 72
}


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

    return summary

# ── Scheduler (started at module level so Passenger/gunicorn picks it up) ─────
_scheduler = BackgroundScheduler(daemon=True)
_FIRST_MATCH_UTC = min(MATCH_KICKOFF_UTC.values())
_scheduler.add_job(sync_scores, 'interval', minutes=2, id='sync_scores',
                   max_instances=1, coalesce=True, start_date=_FIRST_MATCH_UTC)

# ── Static ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/terms')
def terms():
    return send_from_directory('static', 'terms.html')

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

# ── Startup (runs on import — required for Passenger/gunicorn) ────────────────
init_db()
if FOOTBALL_DATA_KEY:
    _scheduler.start()
    atexit.register(lambda: _scheduler.shutdown(wait=False))
    logging.info('Score sync scheduler started (football-data.org, 2-min interval)')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8026, debug=False)
