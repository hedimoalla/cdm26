#!/usr/bin/env python3
"""
Push static/data/match_predictions/*.json to GitHub via Contents API.
Run on Render after export_static.py has generated the files.

Usage:
    python push_match_predictions.py
"""

import os, json, base64, urllib.request, urllib.error

OWNER  = 'hedimoalla'
REPO   = 'cdm26'
BRANCH = 'main'
TOKEN  = os.getenv('GITHUB_TOKEN', '')

BASE_DIR    = os.path.join(os.path.dirname(__file__), 'static', 'data', 'match_predictions')
REPO_PREFIX = 'static/data/match_predictions'

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

    # Check if file already exists (need SHA to update)
    existing, status = api(repo_path)
    sha = existing.get('sha') if status == 200 else None

    body = {
        'message': f'Add {repo_path}',
        'content': content,
        'branch':  BRANCH,
    }
    if sha:
        body['sha'] = sha

    _, status = api(repo_path, method='PUT', body=body)
    return status in (200, 201)

def main():
    if not os.path.isdir(BASE_DIR):
        print(f'ERROR: {BASE_DIR} not found — run export_static.py first')
        return

    files = sorted(f for f in os.listdir(BASE_DIR) if f.endswith('.json'))
    if not files:
        print('No JSON files found in match_predictions/')
        return

    print(f'Pushing {len(files)} files to GitHub...')
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

if __name__ == '__main__':
    main()
