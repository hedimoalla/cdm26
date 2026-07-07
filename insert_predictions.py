"""
One-shot script: insert missing predictions for Ares and Maroo.
Run on the server: python insert_predictions.py
"""
import os, sqlite3
from datetime import datetime

DB = os.getenv('DB_PATH', os.path.join(os.path.dirname(__file__), 'wc2026.db'))

PREDICTIONS = [
    # (username, match_id, home_score, away_score)
    # Ares — R32 matches (all 1-0 home wins)
    ('Ares', 77, 1, 0),   # France vs Sweden
    ('Ares', 79, 1, 0),   # Mexico vs Ecuador
    ('Ares', 80, 1, 0),   # England vs DR Congo
    ('Ares', 81, 1, 0),   # USA vs Bosnia and Herzegovina
    ('Ares', 82, 1, 0),   # Belgium vs Senegal
    ('Ares', 84, 1, 0),   # Spain vs Austria

    # Maroo — R16
    ('Maroo', 90, 0, 1),  # Canada vs Morocco  (away wins)
]

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

try:
    for username, match_id, hs, as_ in PREDICTIONS:
        user = conn.execute(
            "SELECT id FROM users WHERE LOWER(username)=LOWER(?) OR LOWER(nickname)=LOWER(?) OR LOWER(global_name)=LOWER(?)",
            (username, username, username)
        ).fetchone()
        if not user:
            print(f'  ✗ User not found: {username}')
            continue
        uid = user['id']
        conn.execute('''
            INSERT INTO predictions (user_id, match_id, home_score, away_score, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, match_id) DO UPDATE SET
                home_score = excluded.home_score,
                away_score = excluded.away_score,
                updated_at = excluded.updated_at
        ''', (uid, match_id, hs, as_, now, now))
        print(f'  ✓ {username} match {match_id}  {hs}–{as_}')
    conn.commit()
    print('Done.')
finally:
    conn.close()
