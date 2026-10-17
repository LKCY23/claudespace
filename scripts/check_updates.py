#!/usr/bin/env python3
"""Check pinned new resource catalogs. Never modify catalogs or installations."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from resource_catalog import SHA, read_catalog, validate_catalog


class CheckError(RuntimeError):
    pass


class GitHub:
    def __init__(self, token=None):
        self.token = token

    def __call__(self, repo, route):
        headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'claudespace-update-check',
                   'X-GitHub-Api-Version': '2026-03-10'}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        request = Request('https://api.github.com/repos/' + repo + '/' + route, headers=headers)
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as exc:
            raise CheckError('GitHub HTTP ' + str(exc.code)) from None
        except URLError:
            raise CheckError('GitHub transport failed') from None


def check_catalog(catalog, api):
    validate_catalog(catalog)  # Validate all resources before querying anything.
    cache = {}
    def query(repo, route):
        key = repo, route
        if key not in cache:
            try:
                cache[key] = api(repo, route)
            except Exception as exc:
                cache[key] = exc
        if isinstance(cache[key], Exception):
            raise cache[key]
        return cache[key]
    results = []
    for identifier, item in sorted(catalog['resources'].items()):
        ref = identifier + '@' + catalog['name']
        row = {'resource': ref, 'kind': item['kind'], 'agents': sorted(item['compatibility']),
               'maintenance': item['maintenance'], 'strategy': item['update']['strategy']}
        results.append(row)
        if item['update']['strategy'] == 'manual':
            row.update(status='manual', reason='No automatic tracking target')
            continue
        origin = item['origin'].get('upstream', item['source'])
        repo, current = origin['repo'], origin['commit']
        scope = sorted({str(PurePosixPath(path)) for path in
                        [origin['path'], *item['source'].get('imports', {}), *item['source'].get('dependencies', [])]})
        row.update(repo=repo, current_commit=current, target=item['update']['target'], scope=scope)
        try:
            target = item['update']['target']
            if item['update']['strategy'] == 'release':
                release_route = 'releases/latest' if target == 'latest' else 'releases/tags/' + quote(target, safe='')
                release = query(repo, release_route)
                if release.get('draft') or release.get('prerelease') or not isinstance(release.get('tag_name'), str):
                    raise CheckError('Tracking target is not a published full release')
                target = release['tag_name']
                row['release'] = target
            commit = query(repo, 'commits/' + quote(target, safe='')).get('sha')
            if not isinstance(commit, str) or not SHA.fullmatch(commit):
                raise CheckError('Target did not resolve to a full commit SHA')
            row['target_commit'] = commit
            if commit == current:
                row.update(status='no_change', reason='Pinned commit already matches target', changed_files=[])
                continue
            comparison = query(repo, 'compare/' + current + '...' + commit + '?per_page=100&page=1')
            # A rewind/divergence is not a normal forward update. Do not interpret
            # merge-base diffs as an exact current→target resource comparison.
            if comparison.get('status') != 'ahead':
                raise CheckError('Upstream target is not ahead of the pinned commit')
            files = comparison.get('files')
            if not isinstance(files, list):
                raise CheckError('Comparison did not include a file list')
            # GitHub caps compare files at 300, regardless of commit pagination.
            # Without a complete diff, absence of a path cannot establish no change.
            if len(files) >= 300:
                raise CheckError('Comparison file limit reached; full Git comparison required')
            names = set()
            for file in files:
                if not isinstance(file, dict) or not isinstance(file.get('filename'), str):
                    raise CheckError('Malformed comparison file')
                names.add(file['filename'])
                if file.get('previous_filename'):
                    names.add(file['previous_filename'])
            def included(name):
                return any(prefix in ('.', './') or name == prefix.rstrip('/') or name.startswith(prefix.rstrip('/') + '/')
                           for prefix in scope)
            changed = sorted(name for name in names if included(name))
            row.update(status='update_available' if changed else 'no_relevant_change', changed_files=changed,
                       reason='Selected resource paths changed' if changed else 'Only unrelated upstream paths changed',
                       adaptation_required=item['maintenance']['mode'] in ('adapter', 'fork'))
        except Exception as exc:
            row.update(status='check_failed', error_type=type(exc).__name__,
                       reason=str(exc) if isinstance(exc, CheckError) else 'Upstream response/query failed')
    counts = {status: sum(row['status'] == status for row in results)
              for status in ('update_available', 'no_change', 'no_relevant_change', 'manual', 'check_failed')}
    digest = hashlib.sha256(json.dumps(catalog, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'schema_version': 1, 'kind': 'claudespace-update-check', 'catalog': catalog['name'],
            'catalog_fingerprint': digest, 'checked_at': datetime.now(timezone.utc).isoformat(),
            'counts': counts, 'results': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True, help='Explicit new-format catalog file')
    args = parser.parse_args()
    try:
        catalog = read_catalog(args.catalog)
        report = check_catalog(catalog, GitHub(os.environ.get('GITHUB_TOKEN')))
    except (ValueError, OSError) as exc:
        print(json.dumps({'status': 'blocked', 'error_type': type(exc).__name__, 'reason': 'Invalid or unreadable new-format catalog'}))
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if report['counts']['check_failed'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
