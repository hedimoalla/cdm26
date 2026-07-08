"""
fill_missing_predictions.py

For every user with a 100% complete bracket:
  For every knockout match (73-104) that has a locked result:
    - If the user has no main-game prediction, AND
    - their bracket pick for that match was correct (right winner/advancer)
    → Insert a prediction that gives "correct result" only (not exact score).

Usage:
  python fill_missing_predictions.py              # run normally
  python fill_missing_predictions.py --debug      # verbose: show skip reasons for ALL matches
  python fill_missing_predictions.py --debug bazoukatone  # verbose for one user only
"""
import os, json, sqlite3, sys
from datetime import datetime

DEBUG_MODE = '--debug' in sys.argv
DEBUG_USER = None
for i, arg in enumerate(sys.argv):
    if arg == '--debug' and i + 1 < len(sys.argv) and not sys.argv[i+1].startswith('--'):
        DEBUG_USER = sys.argv[i+1].lower()

DB = os.getenv('DB_PATH', os.path.join(os.path.dirname(__file__), 'wc2026.db'))

# ── Bracket structure ─────────────────────────────────────────────────────────

# R32: bracket.r32[i] is the pick for this match ID
R32_SEEDINGS = [74, 77, 73, 75, 83, 84, 81, 82, 76, 78, 79, 80, 86, 88, 85, 87]

# Confirmed R32 home/away teams
R32_HOME_AWAY = {
    73: ('South Africa',           'Canada'),
    74: ('Germany',                'Paraguay'),
    75: ('Netherlands',            'Morocco'),
    76: ('Brazil',                 'Japan'),
    77: ('France',                 'Sweden'),
    78: ('Ivory Coast',            'Norway'),
    79: ('Mexico',                 'Ecuador'),
    80: ('England',                'DR Congo'),
    81: ('USA',                    'Bosnia and Herzegovina'),
    82: ('Belgium',                'Senegal'),
    83: ('Portugal',               'Croatia'),
    84: ('Spain',                  'Austria'),
    85: ('Switzerland',            'Algeria'),
    86: ('Argentina',              'Cape Verde'),
    87: ('Colombia',               'Ghana'),
    88: ('Australia',              'Egypt'),
}

# R16: (match_id, r32_home_slot_index, r32_away_slot_index)
R16_MAP = [
    (89,  0,  1),   # r16[0]: W.74 vs W.77
    (90,  2,  3),   # r16[1]: W.73 vs W.75
    (93,  4,  5),   # r16[2]: W.83 vs W.84
    (94,  6,  7),   # r16[3]: W.81 vs W.82
    (91,  8,  9),   # r16[4]: W.76 vs W.78
    (92, 10, 11),   # r16[5]: W.79 vs W.80
    (95, 12, 13),   # r16[6]: W.86 vs W.88
    (96, 14, 15),   # r16[7]: W.85 vs W.87
]

# QF: (match_id, r16_home_slot_index, r16_away_slot_index)
QF_MAP = [
    (97,  0, 1),   # qf[0]: W.89 vs W.90
    (98,  2, 3),   # qf[1]: W.93 vs W.94
    (99,  4, 5),   # qf[2]: W.91 vs W.92
    (100, 6, 7),   # qf[3]: W.95 vs W.96
]

# SF: (match_id, qf_home_slot_index, qf_away_slot_index)
SF_MAP = [
    (101, 0, 1),   # sf[0]: W.97 vs W.98
    (102, 2, 3),   # sf[1]: W.99 vs W.100
]

# 3rd place: L.101 vs L.102 (SF losers)  → match 103
# Final:     W.101 vs W.102              → match 104


# ── Helpers ───────────────────────────────────────────────────────────────────

def _winner(home_score, away_score, pen_winner, home_team, away_team):
    """Returns (winner_team_name, 'home'|'away'|'draw')."""
    if home_score > away_score:
        return home_team, 'home'
    elif away_score > home_score:
        return away_team, 'away'
    else:
        # Draw at 120' — pen_winner is the advancing team name (or None)
        return pen_winner, 'draw'


def _safe_score(winner_side, actual_h, actual_a):
    """
    Returns (h, a) with the correct outcome sign but never the exact score,
    so only the basic 'correct result' points are awarded.
    """
    if winner_side == 'home':
        return (2, 0) if (actual_h, actual_a) == (1, 0) else (1, 0)
    elif winner_side == 'away':
        return (0, 2) if (actual_h, actual_a) == (0, 1) else (0, 1)
    else:  # draw
        return (1, 1) if (actual_h, actual_a) == (0, 0) else (0, 0)


# ── Main ─────────────────────────────────────────────────────────────────────

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

try:
    # Locked match results
    results_db = {
        r['match_id']: r
        for r in conn.execute(
            'SELECT match_id, score_home, score_away, pen_winner FROM match_results WHERE result_locked=1'
        ).fetchall()
    }

    # ── Build home/away team mapping for every knockout match ─────────────────

    match_home_away = dict(R32_HOME_AWAY)  # starts with R32 hardcoded

    def _resolve_winner(mid, home, away):
        """Resolve actual winner of mid given known home/away teams."""
        r = results_db.get(mid)
        if not r or home is None or away is None:
            return None
        wt, _ = _winner(r['score_home'], r['score_away'], r['pen_winner'], home, away)
        return wt

    # R32 actual winners (indexed by seedings slot)
    r32_actual = [
        _resolve_winner(R32_SEEDINGS[i], *R32_HOME_AWAY[R32_SEEDINGS[i]])
        for i in range(16)
    ]

    # R16
    r16_actual = []
    for mid, hi, ai in R16_MAP:
        home, away = r32_actual[hi], r32_actual[ai]
        if home and away:
            match_home_away[mid] = (home, away)
        r16_actual.append(_resolve_winner(mid, home, away))

    # QF
    qf_actual = []
    for mid, hi, ai in QF_MAP:
        home, away = r16_actual[hi], r16_actual[ai]
        if home and away:
            match_home_away[mid] = (home, away)
        qf_actual.append(_resolve_winner(mid, home, away))

    # SF
    sf_actual = []
    for mid, hi, ai in SF_MAP:
        home, away = qf_actual[hi], qf_actual[ai]
        if home and away:
            match_home_away[mid] = (home, away)
        sf_actual.append(_resolve_winner(mid, home, away))

    # 3rd place: SF losers
    if len(sf_actual) >= 2 and len(qf_actual) >= 4:
        sf_loser_0 = qf_actual[1] if sf_actual[0] == qf_actual[0] else qf_actual[0]
        sf_loser_1 = qf_actual[3] if sf_actual[1] == qf_actual[2] else qf_actual[2]
        if sf_loser_0 and sf_loser_1:
            match_home_away[103] = (sf_loser_0, sf_loser_1)

    # Final
    if len(sf_actual) >= 2 and sf_actual[0] and sf_actual[1]:
        match_home_away[104] = (sf_actual[0], sf_actual[1])

    # ── Flat list of (match_id, round, pick_index) for all bracket matches ───

    bracket_entries = []
    for i, mid in enumerate(R32_SEEDINGS):
        bracket_entries.append((mid, 'r32', i))
    for i, (mid, _, _) in enumerate(R16_MAP):
        bracket_entries.append((mid, 'r16', i))
    for i, (mid, _, _) in enumerate(QF_MAP):
        bracket_entries.append((mid, 'qf', i))
    for i, (mid, _, _) in enumerate(SF_MAP):
        bracket_entries.append((mid, 'sf', i))
    bracket_entries.append((103, 'third', None))
    bracket_entries.append((104, 'final', None))

    # ── Process every user with a bracket ────────────────────────────────────

    total_inserted = 0

    for row in conn.execute(
        'SELECT bp.user_id, bp.picks_json, u.username FROM bracket_picks bp JOIN users u ON u.id=bp.user_id'
    ).fetchall():
        uid      = row['user_id']
        username = row['username']
        picks    = json.loads(row['picks_json'])

        # Must be 100% complete
        r32p  = picks.get('r32') or []
        r16p  = picks.get('r16') or []
        qfp   = picks.get('qf')  or []
        sfp   = picks.get('sf')  or []
        finalp = picks.get('final')
        thirdp = picks.get('third')

        if (len(r32p) != 16 or not all(r32p) or
            len(r16p) != 8  or not all(r16p) or
            len(qfp)  != 4  or not all(qfp)  or
            len(sfp)  != 2  or not all(sfp)  or
            not finalp or not thirdp):
            print(f'  skip {username} — incomplete bracket')
            continue

        # Existing main-game predictions for this user
        existing = {r['match_id'] for r in conn.execute(
            'SELECT match_id FROM predictions WHERE user_id=?', (uid,)
        ).fetchall()}

        verbose = DEBUG_MODE and (DEBUG_USER is None or DEBUG_USER == username.lower())

        user_count = 0
        for mid, rnd, idx in bracket_entries:
            result = results_db.get(mid)
            if not result:
                if verbose:
                    print(f'    · match {mid:>3} ({rnd:<5}) no locked result yet')
                continue  # match not played yet
            if mid in existing:
                if verbose:
                    print(f'    · match {mid:>3} ({rnd:<5}) already has prediction')
                continue  # already has a prediction

            # User's bracket pick for this match
            if rnd == 'final':
                bk_pick = finalp
            elif rnd == 'third':
                bk_pick = thirdp
            else:
                lst = picks.get(rnd) or []
                bk_pick = lst[idx] if idx is not None and idx < len(lst) else None

            if not bk_pick:
                if verbose:
                    print(f'    · match {mid:>3} ({rnd:<5}) no bracket pick')
                continue

            # Actual winner of this match
            home_team, away_team = match_home_away.get(mid, (None, None))
            if not home_team or not away_team:
                print(f'  ⚠  {username}: cannot determine teams for match {mid}')
                continue

            actual_winner, winner_side = _winner(
                result['score_home'], result['score_away'],
                result['pen_winner'], home_team, away_team
            )

            if bk_pick != actual_winner:
                if verbose:
                    print(f'    · match {mid:>3} ({rnd:<5}) pick={bk_pick!r:<32} actual={actual_winner!r}  ✗ wrong')
                continue  # bracket pick was wrong — no points

            # Correct bracket pick → insert prediction with correct result, wrong exact score
            ph, pa = _safe_score(winner_side, result['score_home'], result['score_away'])

            conn.execute('''
                INSERT INTO predictions (user_id, match_id, home_score, away_score, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, match_id) DO NOTHING
            ''', (uid, mid, ph, pa, now, now))

            print(f'    ✓ match {mid:>3} ({rnd:<5}) bk_pick={bk_pick:<30} actual={actual_winner:<30} → {ph}–{pa}')
            user_count += 1

        print(f'  {username}: {user_count} prediction(s) inserted')
        total_inserted += user_count

    conn.commit()
    print(f'\nDone. Total inserted: {total_inserted}')

finally:
    conn.close()
