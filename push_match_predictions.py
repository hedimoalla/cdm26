#!/usr/bin/env python3
"""
Push static/data/match_predictions/*.json to GitHub via Contents API.
Run on Render after export_static.py has generated the files.

Usage — push one batch of 10 (pass the starting match ID):
    python push_match_predictions.py 1    # pushes matches 1-10
    python push_match_predictions.py 11   # pushes matches 11-20
    python push_match_predictions.py 21   # pushes matches 21-30
    python push_match_predictions.py 31   # pushes matches 31-40
    python push_match_predictions.py 41   # pushes matches 41-50
    python push_match_predictions.py 51   # pushes matches 51-60
    python push_match_predictions.py 61   # pushes matches 61-70
    python push_match_predictions.py 71   # pushes matches 71-80
    python push_match_predictions.py 81   # pushes matches 81-90
    python push_match_predictions.py 91   # pushes matches 91-100
    python push_match_predictions.py 101  # pushes matches 101-104

Usage — push all at once (if shell has enough RAM):
    python push_match_predictions.py
"""

import os, sys, json, base64, urllib.request, urllib.error

OWNER  = 'hedimoalla'
REPO   = 'cdm26'
BRANCH = 'main'
TOKEN  = os.getenv('GITHUB_TOKEN', '')

BASE_DIR    = os.path.join(os.path.dirname(__file__), 'static', 'data', 'match_predictions')
REPO_PREFIX = 'static/data/match_predictions'
BATCH_SIZE  = 10

def api(path, method='GET', body=None):
    url = f'https://api.github.com/repos/{OWNER}/{REPO}/contents/{path}'
    req = urllib.request.Request(url, method=method)
    req.add_header('Authorization', f'token {TOKEN}')
    req.add_header('Accept', 'application/vnd.github+json')
    if body:
        req.add_header('Content-Type', 'application/json')
        req.data = json.dumps(body).encode()
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code

def push_file(local_path, repo_path):
    with open(local_path, 'rb') as f:
        content = base64.b64encode(f.read()).decode()
    existing, status = api(repo_path)
    sha = existing.get('sha') if status == 200 else None
    body = {'message': f'Add {repo_path}', 'content': content, 'branch': BRANCH}
    if sha:
        body['sha'] = sha
    _, status = api(repo_path, method='PUT', body=body)
    return status in (200, 201)

def main():
    if not TOKEN:
        print('ERROR: set GITHUB_TOKEN env var')
        sys.exit(1)

    if not os.path.isdir(BASE_DIR):
        print(f'ERROR: {BASE_DIR} not found — run export_static.py first')
        sys.exit(1)

    # Sort numerically by match ID
    all_files = sorted(
        (f for f in os.listdir(BASE_DIR) if f.endswith('.json')),
        key=lambda f: int(f.replace('.json', ''))
    )
    if not all_files:
        print('No JSON files found in match_predictions/')
        sys.exit(1)

    # Determine slice from optional start argument
    if len(sys.argv) > 1:
        start = int(sys.argv[1])
        end   = start + BATCH_SIZE
        files = [f for f in all_files if start <= int(f.replace('.json', '')) < end]
        print(f'Batch: matches {start}–{end - 1} ({len(files)} files)')
    else:
        files = all_files
        print(f'Pushing all {len(files)} files...')

    ok = fail = 0
    for fname in files:
        local  = os.path.join(BASE_DIR, fname)
        remote = f'{REPO_PREFIX}/{fname}'
        if push_file(local, remote):
            print(f'  ✓ {fname}')
            ok += 1
        else:
            print(f'  ✗ {fname} FAILED')
            fail += 1

    print(f'\nDone: {ok} pushed, {fail} failed.')
    if fail:
        print('Re-run with the same start ID to retry failed files.')

if __name__ == '__main__':
    main()
