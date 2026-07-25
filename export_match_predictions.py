#!/usr/bin/env python3
"""
Export match predictions to static JSON — one file per locked match.
Run in batches to avoid RAM issues on Render.

Usage:
    python export_match_predictions.py 1    # exports matches 1-10
    python export_match_predictions.py 11   # exports matches 11-20
    python export_match_predictions.py 21   # exports matches 21-30
    python export_match_predictions.py 31   # exports matches 31-40
    python export_match_predictions.py 41   # exports matches 41-50
    python export_match_predictions.py 51   # exports matches 51-60
    python export_match_predictions.py 61   # exports matches 61-70
    python export_match_predictions.py 71   # exports matches 71-80
    python export_match_predictions.py 81   # exports matches 81-90
    python export_match_predictions.py 91   # exports matches 91-100
    python export_match_predictions.py 101  # exports matches 101-110 (covers 101-104)
"""

import os, sys, json, sqlite3
from contextlib import contextmanager

DB_PATH    = os.getenv('DB_PATH', os.path.join(os.path.dirname(__file__), 'wc2026.db'))
OUT_DIR    = os.path.join(os.path.dirname(__file__), 'static', 'data', 'match_predictions')
BATCH_SIZE = 10

@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn.cursor()
    finally:
        conn.close()

def main():
    if not os.path.exists(DB_PATH):
        sys.exit(f'ERROR: DB not found at {DB_PATH}\nSet DB_PATH env var.')

    start = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    end   = start + BATCH_SIZE

    os.makedirs(OUT_DIR, exist_ok=True)

    with db() as c:
        locked_ids = sorted(
            r['match_id'] for r in c.execute(
                'SELECT match_id FROM match_results WHERE result_locked=1 AND match_id>=? AND match_id<?',
                (start, end)
            ).fetchall()
        )

    if not locked_ids:
        print(f'No locked matches found in range {start}-{end-1}.')
        return

    print(f'Exporting {len(locked_ids)} matches ({start}-{end-1})...')

    for mid in locked_ids:
        with db() as c:
            rows = c.execute('''
                SELECT u.id, u.global_name, u.username, u.avatar, u.nickname,
                       p.home_score, p.away_score
                FROM predictions p
                JOIN users u ON u.id = p.user_id
                WHERE p.match_id = ?
                ORDER BY COALESCE(u.nickname, u.global_name, u.username) COLLATE NOCASE
            ''', (mid,)).fetchall()

        predictions = [{
            'id':           r['id'],
            'display_name': r['nickname'] or r['global_name'] or r['username'],
            'avatar':       r['avatar'],
            'home_score':   r['home_score'],
            'away_score':   r['away_score'],
        } for r in rows]

        path = os.path.join(OUT_DIR, f'{mid}.json')
        with open(path, 'w') as f:
            json.dump({'predictions': predictions, 'locked': True}, f, separators=(',', ':'))
        print(f'  ✓ {mid}.json ({len(predictions)} predictions)')

    print(f'\nDone. Now run:')
    print(f'  GITHUB_TOKEN=<token> python push_match_predictions.py {start}')

if __name__ == '__main__':
    main()
