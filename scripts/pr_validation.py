#!/usr/bin/env python3
"""Select and report exact-head PR checks using trusted default-branch code."""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import quote

from resource_catalog import SHA, require
from sync_update_prs import GitHubPRs
from auto_merge import marketplace_only, disable_owned


def eligible(pr, repo, base, expected):
    return (pr['state'] == 'open' and pr['base']['ref'] == base
            and pr['base']['repo']['full_name'] == repo
            and pr['head']['repo'] is not None and pr['head']['repo']['full_name'] == repo
            and pr['head']['sha'] == expected)


def select(hub, event, *, number='', expected=''):
    base = hub.api('GET', '')['default_branch']
    if 'workflow_run' in event:
        run = hub.api('GET', 'actions/runs/' + str(int(event['workflow_run']['id'])))
        if (run['event'] != 'pull_request' or run['path'] != '.github/workflows/validate-resources.yml'
                or run['head_repository']['full_name'] != hub.repo):
            return None
        expected = run['head_sha']
        query = quote(hub.repo.split('/')[0] + ':' + run['head_branch'], safe='')
        prs = hub.api('GET', 'pulls?state=open&head=' + query + '&per_page=100')
        if len(prs) != 1:
            return None
        pr = prs[0]
    else:
        require(str(number).isdigit() and int(number) > 0, 'Supply a PR number')
        pr = hub.api('GET', 'pulls/' + str(int(number)))
    require(isinstance(expected, str) and SHA.fullmatch(expected), 'Supply an exact PR head SHA')
    return pr if eligible(pr, hub.repo, base, expected) else None


def status(hub, sha, context, state, url, description):
    hub.api('POST', 'statuses/' + sha, {'context': context, 'state': state,
                                     'target_url': url, 'description': description})


def finish(hub, number, expected, tooling, fixed, url):
    require(SHA.fullmatch(expected), 'Invalid result SHA')
    base = hub.api('GET', '')['default_branch']
    pr = hub.api('GET', 'pulls/' + str(int(number)))
    if not eligible(pr, hub.repo, base, expected):
        return 'superseded'
    passed = tooling == 'success' and fixed == 'success'
    automatic = passed and marketplace_only(hub, pr)
    if not automatic: disable_owned(hub, pr)
    status(hub, expected, 'Tooling tests', 'success' if tooling == 'success' else 'failure', url,
           'Exact-head tests and generated marketplace checks: ' + tooling)
    if fixed != 'success':
        status(hub, expected, 'claudespace/fixed-sources', 'failure', url,
               'Trusted fixed-source job did not succeed: ' + fixed)
    if automatic and hub.api('GET', '').get('allow_auto_merge'):
        fresh = hub.api('GET', 'pulls/' + str(int(number)))
        if not eligible(fresh, hub.repo, base, expected) or not marketplace_only(hub, fresh): return 'superseded'
        hub.command('merge', str(int(number)), '--auto', '--squash', '--match-head-commit', expected)
        return 'auto-merge-requested: generated marketplaces only'
    return 'ready-for-review' if passed else 'needs-attention'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('select', 'report'))
    parser.add_argument('--repo', required=True)
    args = parser.parse_args()
    hub = GitHubPRs(args.repo)
    url = os.environ['GITHUB_SERVER_URL'] + '/' + args.repo + '/actions/runs/' + os.environ['GITHUB_RUN_ID']
    if args.operation == 'select':
        event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
        pr = select(hub, event, number=os.environ.get('PR_NUMBER', ''), expected=os.environ.get('PR_HEAD', ''))
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            stream.write('eligible=' + ('true' if pr else 'false') + '\n')
            if pr:
                sha = pr['head']['sha']
                stream.write('number=' + str(pr['number']) + '\nhead=' + sha + '\n')
                for context in ('Tooling tests', 'claudespace/fixed-sources'):
                    status(hub, sha, context, 'pending', url, 'Exact-head PR validation is running')
        summary = ('PR #' + str(pr['number']) + ' · ' + pr['head']['sha']) if pr else 'Skipped: closed, superseded, fork, or unrelated run.'
    else:
        summary = finish(hub, os.environ['PR_NUMBER'], os.environ['PR_HEAD'],
                         os.environ['TOOLING_RESULT'], os.environ['FIXED_RESULT'], url)
    print(summary)
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
        stream.write('## PR validation\n\n' + summary + '\n')


if __name__ == '__main__':
    main()
