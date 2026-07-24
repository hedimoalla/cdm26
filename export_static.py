#!/usr/bin/env python3
"""
Export all dynamic DB data to static JSON files in static/data/.

Run once on Render (via Shell) before dropping the persistent disk:
    python export_static.py

Or point at a local DB copy:
    DB_PATH=/path/to/wc2026.db python export_static.py

Output files (all served as /data/*.json by the static Flask fallback):
    static/data/results.json
    static/data/leaderboard.json
    static/data/leaderboard_alt.json
    static/data/bracket_leaderboard.json
    static/data/profiles/<user_id>.json
    static/data/bracket_picks/<user_id>.json
"""

import os, sys, json, sqlite3
from contextlib import contextmanager

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH    = os.getenv('DB_PATH', os.path.join(os.path.dirname(__file__), 'wc2026.db'))
OUT_DIR    = os.path.join(os.path.dirname(__file__), 'static', 'data')

# ── Match metadata (must match app.py) ───────────────────────────────────────
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

STAGE_PTS = {
    'group': (1, 3), 'r32': (3, 6), 'r16': (3, 6),
    'qf': (5, 8), 'sf': (7, 15), 'third': (7, 15), 'final': (10, 20),
}

# ── Helpers ───────────────────────────────────────────────────────────────────
@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, separators=(',', ':'))
    print(f'  wrote {os.path.relpath(path)}')

def calc_pts(ph, pa, sh, sa, stage, total_preds, same_score_count):
    outcome_pts, exact_pts = STAGE_PTS.get(stage, (0, 0))
    if ph == sh and pa == sa:
        p = exact_pts
        if same_score_count < max(1, total_preds * (0.15 if stage == 'group' else 0.12)):
            p += 5 if stage == 'group' else 10
        return p
    if ((ph > pa) - (ph < pa)) == ((sh > sa) - (sh < sa)):
        return outcome_pts
    return 0

def calc_pts_gd(ph, pa, sh, sa, stage, total_preds, same_score_count):
    pts = calc_pts(ph, pa, sh, sa, stage, total_preds, same_score_count)
    if pts > 0 and (ph - pa) == (sh - sa):
        pts += 2
    return pts

def build_rarity(c, result_map):
    """Return {match_id: (total, same)} for all finished matches."""
    totals = {r['match_id']: r['cnt'] for r in c.execute(
        'SELECT match_id, COUNT(*) cnt FROM predictions GROUP BY match_id'
    ).fetchall()}
    same_counts = {r['match_id']: r['cnt'] for r in c.execute(
        '''SELECT p.match_id, COUNT(*) cnt FROM predictions p
           JOIN match_results r ON p.match_id=r.match_id
             AND p.home_score=r.score_home AND p.away_score=r.score_away
           WHERE r.result_locked=1 GROUP BY p.match_id'''
    ).fetchall()}
    return {mid: (totals.get(mid, 0), same_counts.get(mid, 0)) for mid in result_map}

# ── Exporters ─────────────────────────────────────────────────────────────────
def export_results(c):
    rows = c.execute('''
        SELECT mr.match_id, mr.score_home, mr.score_away, mr.result_locked, mr.pen_winner,
               COALESCE(mm.status,'FINISHED') AS status,
               COALESCE(mm.admin_unlocked, 0) AS admin_unlocked
        FROM match_results mr
        LEFT JOIN match_meta mm ON mm.match_id = mr.match_id
    ''').fetchall()
    result_map = {
        str(r['match_id']): {
            'home': r['score_home'],
            'away': r['score_away'],
            'locked': bool(r['result_locked']),
            'status': r['status'],
            'admin_unlocked': bool(r['admin_unlocked']),
            **({'pen_winner': r['pen_winner']} if r['pen_winner'] else {}),
        }
        for r in rows
    }
    unlocked = [r['match_id'] for r in c.execute(
        'SELECT match_id FROM match_meta WHERE admin_unlocked=1'
    ).fetchall()]
    write_json(os.path.join(OUT_DIR, 'results.json'),
               {'results': result_map, 'admin_unlocked': unlocked})

def export_leaderboard(c, result_map, rarity, alt=False):
    users = c.execute('SELECT id, username, global_name, avatar, nickname FROM users').fetchall()
    board = []
    for user in users:
        preds = {r['match_id']: (r['home_score'], r['away_score'])
                 for r in c.execute(
                     'SELECT match_id, home_score, away_score FROM predictions WHERE user_id=?',
                     (user['id'],)).fetchall()}
        pts = bonus = exact = good = gd_bonus = 0
        for mid, (sh, sa) in result_map.items():
            if mid not in preds:
                continue
            ph, pa = preds[mid]
            total_p, same_p = rarity[mid]
            stage = MATCH_STAGE[mid]
            base = calc_pts(ph, pa, sh, sa, stage, total_p, same_p)
            gd_extra = 2 if alt and base > 0 and (ph - pa) == (sh - sa) else 0
            pts += base + gd_extra
            if gd_extra:
                gd_bonus += 1
            if ph == sh and pa == sa:
                exact += 1
                if same_p < max(1, total_p * (0.15 if stage == 'group' else 0.12)):
                    bonus += 1
            elif ((ph > pa) - (ph < pa)) == ((sh > sa) - (sh < sa)):
                good += 1
        entry = {
            'user_id':     user['id'],
            'name':        user['nickname'] or user['global_name'] or user['username'],
            'avatar':      user['avatar'],
            'points':      pts,
            'predictions': len(preds),
            'bonus':       bonus,
            'exact':       exact,
            'good':        good,
        }
        if alt:
            entry['gd_bonus'] = gd_bonus
        board.append(entry)

    if alt:
        board.sort(key=lambda x: (-x['points'], -x['gd_bonus'], -x['exact'], -x['good'], -x['bonus'], x['name'].lower(), x['user_id']))
    else:
        board.sort(key=lambda x: (-x['points'], -x['exact'], -x['good'], -x['bonus'], x['name'].lower(), x['user_id']))

    fname = 'leaderboard_alt.json' if alt else 'leaderboard.json'
    write_json(os.path.join(OUT_DIR, fname),
               {'leaderboard': board, 'scored_matches': len(result_map)})

def export_profiles(c, result_map, rarity):
    users = c.execute('SELECT id, username, global_name, avatar, nickname FROM users').fetchall()
    for user in users:
        uid = user['id']
        preds_raw = c.execute(
            'SELECT match_id, home_score, away_score FROM predictions WHERE user_id=?', (uid,)
        ).fetchall()
        preds = {r['match_id']: (r['home_score'], r['away_score']) for r in preds_raw}

        predictions = []
        for mid, (sh, sa) in result_map.items():
            if mid not in preds:
                continue
            ph, pa = preds[mid]
            total_p, same_p = rarity.get(mid, (0, 0))
            p = calc_pts(ph, pa, sh, sa, MATCH_STAGE[mid], total_p, same_p)
            predictions.append({
                'match_id':    mid,
                'home_score':  ph,
                'away_score':  pa,
                'result_home': sh,
                'result_away': sa,
                'points':      p,
                'stage':       MATCH_STAGE[mid],
            })
        predictions.sort(key=lambda x: x['match_id'])

        def sign(x): return (x > 0) - (x < 0)
        pts_total = sum(p['points'] for p in predictions)
        exact = sum(1 for p in predictions if p['home_score'] == p['result_home'] and p['away_score'] == p['result_away'])
        good  = sum(1 for p in predictions
                    if not (p['home_score'] == p['result_home'] and p['away_score'] == p['result_away'])
                    and sign(p['home_score'] - p['away_score']) == sign(p['result_home'] - p['result_away']))

        write_json(os.path.join(OUT_DIR, 'profiles', f'{uid}.json'), {
            'user': {
                'id':     uid,
                'name':   user['nickname'] or user['global_name'] or user['username'],
                'avatar': user['avatar'],
            },
            'stats': {'points': pts_total, 'predictions': len(preds), 'exact': exact, 'good': good},
            'predictions': predictions,
        })

BRACKET_PTS = {'r32': 5, 'r16': 5, 'qf': 10, 'sf': 20, 'final': 40, 'third': 20}

def _calc_bracket_score(picks, results):
    pts = 0
    for rnd in ('r32', 'r16', 'qf', 'sf'):
        ppick = BRACKET_PTS[rnd]
        real  = results.get(rnd) or []
        user  = picks.get(rnd) or []
        for i, real_team in enumerate(real):
            if real_team and i < len(user) and user[i] == real_team:
                pts += ppick
    if results.get('final') and picks.get('final') == results['final']:
        pts += BRACKET_PTS['final']
    if results.get('third') and picks.get('third') == results['third']:
        pts += BRACKET_PTS['third']
    return pts

def _bracket_tiebreaker(picks, results):
    def count_correct(rnd):
        real = results.get(rnd) or []
        user = picks.get(rnd) or []
        return sum(1 for i, t in enumerate(real) if t and i < len(user) and user[i] == t)
    champ         = 1 if results.get('final') and picks.get('final') == results['final'] else 0
    sf_correct    = count_correct('sf')
    third_correct = 1 if results.get('third') and picks.get('third') == results['third'] else 0
    correct_final  = 1 if sf_correct == 2 else 0
    correct_podium = 1 if (champ and correct_final and third_correct) else 0
    qf_correct    = count_correct('qf')
    r16_correct   = count_correct('r16')
    total_correct = (count_correct('r32') + count_correct('r16') + count_correct('qf') +
                     sf_correct + champ + third_correct)
    return (champ, correct_final, correct_podium, qf_correct, r16_correct, total_correct)

def export_bracket(c):
    try:
        state = c.execute('SELECT * FROM bracket_state WHERE id=1').fetchone()
    except Exception:
        print('  bracket_state table not found, skipping bracket export')
        return

    results = json.loads(state['results_json']) if state and state['results_json'] else {}

    rows = c.execute('''
        SELECT bp.user_id, bp.picks_json, bp.score, bp.updated_at,
               u.username, u.global_name, u.avatar, u.nickname
        FROM bracket_picks bp
        JOIN users u ON u.id = bp.user_id
    ''').fetchall()

    board = []
    for row in rows:
        picks = json.loads(row['picks_json'])
        score = _calc_bracket_score(picks, results)
        tb    = _bracket_tiebreaker(picks, results)
        board.append({
            'user_id':    row['user_id'],
            'name':       row['nickname'] or row['global_name'] or row['username'],
            'avatar':     row['avatar'],
            'score':      score,
            'updated_at': row['updated_at'],
            '_tb':        tb,
        })

    board.sort(key=lambda x: (-x['score'], *[-v for v in x['_tb']], x['name'].lower()))
    for e in board:
        del e['_tb']

    write_json(os.path.join(OUT_DIR, 'bracket_leaderboard.json'), {
        'leaderboard':    board,
        'bracket_status': state['status'] if state else 'closed',
    })

    # Per-user bracket picks
    slots_row = state['slots_json'] if state else None
    for row in rows:
        uid   = row['user_id']
        picks = json.loads(row['picks_json'])
        score = _calc_bracket_score(picks, results)
        write_json(os.path.join(OUT_DIR, 'bracket_picks', f'{uid}.json'), {
            'picks': picks,
            'score': score,
        })

    # Bracket state (slots + results) for rendering
    write_json(os.path.join(OUT_DIR, 'bracket_state.json'), {
        'status':   state['status'] if state else 'closed',
        'slots':    json.loads(slots_row) if slots_row else [],
        'results':  results,
    })

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not os.path.exists(DB_PATH):
        sys.exit(f'ERROR: DB not found at {DB_PATH}\nSet DB_PATH env var or copy wc2026.db here.')

    print(f'Reading DB: {DB_PATH}')
    print(f'Output dir: {OUT_DIR}')
    print()

    with db() as c:
        # Results (needed by multiple exporters)
        result_rows = c.execute(
            'SELECT match_id, score_home, score_away FROM match_results WHERE result_locked=1'
        ).fetchall()
        result_map = {r['match_id']: (r['score_home'], r['score_away']) for r in result_rows}
        rarity = build_rarity(c, result_map)

        print('Exporting results...')
        export_results(c)

        print('Exporting leaderboard...')
        export_leaderboard(c, result_map, rarity, alt=False)

        print('Exporting leaderboard (GD bonus)...')
        export_leaderboard(c, result_map, rarity, alt=True)

        print('Exporting user profiles...')
        export_profiles(c, result_map, rarity)

        print('Exporting bracket...')
        export_bracket(c)

    print()
    print('Done. Commit static/data/ to git, then drop the persistent disk.')

if __name__ == '__main__':
    main()
