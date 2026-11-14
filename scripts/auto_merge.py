"""Small automatic-merge boundary: deterministic generated marketplaces only."""
import base64
import json
from urllib.parse import quote
from sync_marketplaces import render


def marketplace_only(hub, pr):
    if pr.get('draft', True) or pr.get('user', {}).get('login') != 'github-actions[bot]':
        return False
    files = hub.api('GET', 'pulls/'+str(pr['number'])+'/files?per_page=100')
    if not files or len(files) >= 100 or len(files) != pr.get('changed_files'):
        return False
    cache = {}
    def read(sha, path):
        key = sha, path
        if key not in cache:
            value = hub.api('GET', 'contents/'+quote(path, safe='/')+'?ref='+sha)
            if value.get('type') != 'file' or value.get('encoding') != 'base64':
                raise ValueError('Expected a regular generated file')
            cache[key] = base64.b64decode(value['content'])
        return cache[key]
    try:
        base = pr['base']['sha']; head = pr['head']['sha']
        config = json.loads(read(base, 'marketplaces.json'))
        allowed = {row['output'] for row in config['marketplaces']}
        if any(row['filename'] not in allowed or row['status'] not in ('added','modified')
               or 'previous_filename' in row for row in files): return False
        expected = render(lambda path: read(base, path))
        return all(read(head, path) == content for path, content in expected.items())
    except (ValueError, KeyError, TypeError): return False


def disable_owned(hub, pr):
    if (pr.get('auto_merge') or {}).get('enabled_by', {}).get('login') == 'github-actions[bot]':
        hub.command('merge', str(pr['number']), '--disable-auto')
