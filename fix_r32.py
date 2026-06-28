"""
One-shot script: set the confirmed R32 bracket slots, open the bracket,
and unlock all 16 R32 matches for predictions.

Run on the server: python fix_r32.py
"""
import os
import json
import sqlite3

DB = os.getenv('DB_PATH', os.path.join(os.path.dirname(__file__), 'wc2026.db'))

R32_SLOTS = [
    {'pos':  1, 'team': 'Germany'},                  # E1
    {'pos':  2, 'team': 'Paraguay'},                  # D3 best-3rd  → match 74
    {'pos':  3, 'team': 'France'},                    # I1
    {'pos':  4, 'team': 'Sweden'},                    # F3 best-3rd  → match 77
    {'pos':  5, 'team': 'South Africa'},              # A2
    {'pos':  6, 'team': 'Canada'},                    # B2
    {'pos':  7, 'team': 'Netherlands'},               # F1
    {'pos':  8, 'team': 'Morocco'},                   # C2
    {'pos':  9, 'team': 'Portugal'},                  # K2
    {'pos': 10, 'team': 'Croatia'},                   # L2
    {'pos': 11, 'team': 'Spain'},                     # H1
    {'pos': 12, 'team': 'Austria'},                   # J2
    {'pos': 13, 'team': 'USA'},                       # D1
    {'pos': 14, 'team': 'Bosnia and Herzegovina'},    # B3 best-3rd  → match 81
    {'pos': 15, 'team': 'Belgium'},                   # G1
    {'pos': 16, 'team': 'Senegal'},                   # I3 best-3rd  → match 82
    {'pos': 17, 'team': 'Brazil'},                    # C1
    {'pos': 18, 'team': 'Japan'},                     # F2
    {'pos': 19, 'team': 'Ivory Coast'},               # E2
    {'pos': 20, 'team': 'Norway'},                    # I2
    {'pos': 21, 'team': 'Mexico'},                    # A1
    {'pos': 22, 'team': 'Ecuador'},                   # E3 best-3rd  → match 79
    {'pos': 23, 'team': 'England'},                   # L1
    {'pos': 24, 'team': 'DR Congo'},                  # K3 best-3rd  → match 80
    {'pos': 25, 'team': 'Argentina'},                 # J1
    {'pos': 26, 'team': 'Cape Verde'},                # H2
    {'pos': 27, 'team': 'Australia'},                 # D2
    {'pos': 28, 'team': 'Egypt'},                     # G2
    {'pos': 29, 'team': 'Switzerland'},               # B1
    {'pos': 30, 'team': 'Algeria'},                   # J3 best-3rd  → match 85
    {'pos': 31, 'team': 'Colombia'},                  # K1
    {'pos': 32, 'team': 'Ghana'},                     # L3 best-3rd  → match 87
]

R32_MATCH_IDS = list(range(73, 89))  # 73-88 inclusive

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
try:
    conn.execute('''
        INSERT INTO bracket_state (id, slots_json, status) VALUES (1, ?, 'open')
        ON CONFLICT(id) DO UPDATE SET
            slots_json = excluded.slots_json,
            status     = 'open',
            updated_at = datetime('now')
    ''', (json.dumps(R32_SLOTS),))

    for mid in R32_MATCH_IDS:
        conn.execute('''
            INSERT INTO match_meta (match_id, status, admin_unlocked)
            VALUES (?, 'UPCOMING', 1)
            ON CONFLICT(match_id) DO UPDATE SET admin_unlocked = 1
        ''', (mid,))

    conn.commit()
    print(f'Done. Bracket opened with {len(R32_SLOTS)} slots. Matches unlocked: {R32_MATCH_IDS}')
finally:
    conn.close()
