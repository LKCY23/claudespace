#!/usr/bin/env python3
"""Preview or synchronize bot-owned update PRs from validated Git bundles."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import quote

from build_candidates import within, write_json
from candidate_sources import git
from prepare_update import advance_catalog, advance_discovery, clean_head, protect_local_sources, selected_updates
from resource_catalog import NAME, REPO, SHA, require, validate_catalog

PREFIX = '<!-- claudespace-update-v1\n'
SUFFIX = '\n-->'


def title(state):
    return 'chore: update ' + state['branch'].rsplit('/', 1)[-1] + ' (' + state['catalog'] + ')'


def body(state):
    lines = ['更新以下固定资源来源，供人工审查后合并。', '', '| 资源 | 原提交 | 新提交 |', '| --- | --- | --- |']
    for name, row in sorted(state['updates'].items()):
        url = 'https://github.com/' + row['repo'] + '/compare/' + row['from_commit'] + '...' + row['to_commit']
        lines.append('| ' + name + ' | `' + row['from_commit'][:12] + '` | [' + row['to_commit'][:12] + '](' + url + ') |')
    lines += ['', '验证：候选准备阶段的来源与结构检查通过；PR CI 状态以本 PR 的 Checks 为准。',
              '原生加载、账号和实际业务未验证。本 PR 不改变个人 Profile、启用状态或本机安装。', '',
              PREFIX + json.dumps(state, ensure_ascii=False, sort_keys=True) + SUFFIX]
    return '\n'.join(lines)


def marker(pr, repo, base, branch, bot):
    require(pr['user']['login'] == bot and pr['head']['repo']['full_name'] == repo and pr['base']['ref'] == base and pr['head']['ref'] == branch,
            'PR identity/author differs from this automation; preserve it')
    text = pr.get('body') or ''
    require(text.count(PREFIX) == 1 and text.endswith(SUFFIX), 'PR has no unique automation record; preserve it')
    state = json.loads(text.split(PREFIX, 1)[1][:-len(SUFFIX)])
    require(state.get('schema_version') == 1 and state.get('repo') == repo and state.get('branch') == branch,
            'PR automation record belongs to another candidate')
    require(pr.get('title') == title(state) and text == body(state), 'PR text was edited manually; preserve it')
    return state


def same_scope(a, b):
    return all(a[key] == b[key] for key in ('repo', 'base', 'branch', 'catalog', 'catalog_path')) and set(a['updates']) == set(b['updates'])


def managed_pr(pr):
    """Observe only identity and fields this publisher may replace."""
    if pr is None:
        return None
    return (pr['number'], pr['state'], pr.get('merged_at'), pr.get('title'), pr.get('body'),
            pr['user']['login'], pr['head']['repo']['full_name'], pr['head']['ref'], pr['base']['ref'])


def decide(state, remote, bot):
    require(remote['base_sha'] == state['base_commit'], 'Default branch advanced; prepare a new candidate')
    pr, head = remote['pr'], remote['head_sha']
    old = None
    if pr:
        old = marker(pr, state['repo'], state['base'], state['branch'], bot)
        require(same_scope(old, state), 'The update group changed; review the existing PR before reusing it')
        if pr['state'] == 'closed' and not pr.get('merged_at') and old['updates'] == state['updates']:
            return {'action': 'declined', 'expected_head': head, 'pr_number': pr['number']}
        require(head in (None, old['generated_head'], state['generated_head']), 'Candidate branch has manual commits; preserve them')
        if pr['state'] == 'open':
            require(head is not None, 'Open PR branch is missing')
            if old['base_commit'] == state['base_commit'] and old['tree'] == state['tree'] and old['updates'] == state['updates'] and head == old['generated_head']:
                return {'action': 'unchanged', 'expected_head': head, 'pr_number': pr['number']}
    elif head is not None:
        require(head == state['generated_head'], 'Existing branch has no matching automation PR; preserve it')
    return {'action': 'update' if pr and pr['state'] == 'open' else 'create', 'expected_head': head,
            'pr_number': pr['number'] if pr and pr['state'] == 'open' else None}


class GitHubPRs:
    def __init__(self, repo):
        require(REPO.fullmatch(repo), 'Invalid GitHub repository')
        self.repo = repo

    def api(self, method, route, payload=None, missing=False):
        args = ['gh', 'api', '--method', method, 'repos/' + self.repo + '/' + route]
        if payload is not None: args += ['--input', '-']
        result = subprocess.run(args, input=json.dumps(payload) if payload is not None else None, capture_output=True, text=True, timeout=45)
        if result.returncode:
            if missing and '(HTTP 404)' in result.stderr: return None
            raise ValueError('GitHub ' + method + ' failed; check repository/token permissions and the saved operation report')
        return json.loads(result.stdout)

    def inspect(self, branch, base):
        tip = self.api('GET', 'git/ref/heads/' + quote(base, safe=''))
        ref = self.api('GET', 'git/ref/heads/' + quote(branch, safe=''), missing=True)
        query = 'head=' + quote(self.repo.split('/')[0] + ':' + branch, safe='') + '&base=' + quote(base, safe='')
        opened = self.api('GET', 'pulls?state=open&' + query + '&per_page=100')
        require(len(opened) <= 1, 'Multiple open PRs match the update branch')
        closed = [] if opened else self.api('GET', 'pulls?state=closed&' + query + '&sort=updated&direction=desc&per_page=1')
        return {'base_sha': tip['object']['sha'], 'head_sha': ref['object']['sha'] if ref else None, 'pr': (opened or closed or [None])[0]}

    def push(self, objects, commit, branch, expected):
        ref = 'refs/heads/' + branch
        git(objects, '-c', 'credential.helper=', '-c', 'credential.helper=!gh auth git-credential',
            'push', '--porcelain', '--force-with-lease=' + ref + ':' + (expected or ''),
            'https://github.com/' + self.repo + '.git', commit + ':' + ref)

    def create(self, state):
        return self.api('POST', 'pulls', {'head': state['branch'], 'base': state['base'], 'title': title(state), 'body': body(state), 'draft': True})

    def update(self, number, state):
        return self.api('PATCH', 'pulls/' + str(number), {'title': title(state), 'body': body(state)})


def inspect_bundle(root, bundle, receipt, objects, repo, base):
    require(receipt.get('schema_version') == 1 and receipt.get('kind') == 'claudespace-source-candidate' and receipt.get('status') in ('prepared', 'reused'), 'Invalid candidate receipt')
    request = receipt['request']; head = receipt['candidate_commit']
    require(SHA.fullmatch(head) and SHA.fullmatch(request['base_commit']), 'Invalid fixed candidate commits')
    require(clean_head(root) == request['base_commit'], 'Publisher checkout differs from the prepared base')
    remote = request['base_repository'].removesuffix('.git')
    require(remote in ('https://github.com/' + repo, 'git@github.com:' + repo, 'ssh://git@github.com/' + repo), 'Candidate belongs to another repository')
    git(root, 'check-ref-format', '--branch', request['branch'])
    require(request['branch'].startswith('claudespace/update/'), 'Refusing to write outside update branches')
    git(root, 'clone', '--quiet', '--bare', '--no-hardlinks', str(root), str(objects))
    git(objects, 'bundle', 'verify', str(bundle))
    git(objects, 'fetch', '--quiet', '--no-tags', str(bundle), request['branch'])
    require(git(objects, 'rev-parse', 'FETCH_HEAD').decode().strip() == head, 'Bundle head differs from its receipt')
    require(git(objects, 'rev-list', '--parents', '-n', '1', head).decode().split() == [head, request['base_commit']], 'Candidate must be one prepared commit on its declared base')
    path = request['catalog_path']
    require(not Path(path).is_absolute() and '..' not in Path(path).parts, 'Invalid catalog path')
    before = json.loads(git(objects, 'show', request['base_commit'] + ':' + path))
    after = json.loads(git(objects, 'show', head + ':' + path))
    validate_catalog(before); validate_catalog(after)
    prefix = 'claudespace/update/' + before['name'] + '/'
    require(request['branch'] != base and request['branch'].startswith(prefix)
            and NAME.fullmatch(request['branch'][len(prefix):]), 'Candidate branch does not match its catalog or targets the base branch')
    checked = {'schema_version': 1, 'kind': 'claudespace-update-check', 'catalog': before['name'], 'catalog_fingerprint': request['catalog_fingerprint'],
               'results': [{'resource': name + '@' + before['name'], 'status': 'update_available', 'repo': row['repo'],
                            'current_commit': row['from_commit'], 'target_commit': row['to_commit']} for name, row in request['updates'].items()]}
    updates = selected_updates(before, checked, list(request['updates']))
    protect_local_sources(before, updates, root / Path(path).parent)
    require(after == advance_catalog(before, updates), 'Candidate changed settings outside the selected version update')
    parent = Path(path).parent
    discovery = [parent / '.claude-plugin/marketplace.json', parent / '.agents/plugins/marketplace.json']
    allowed = [Path(path), *discovery]
    allowed += [parent / before['resources'][name]['source']['path'] for name in updates if before['resources'][name]['source']['kind'] != 'external']
    changed = git(objects, 'diff', '--name-only', '-z', request['base_commit'], head).split(b'\0')
    require(all(not name or any(Path(name.decode()).is_relative_to(p) for p in allowed) for name in changed), 'Candidate changed files outside its resource scope')
    for manifest_path in discovery:
        if manifest_path.as_posix().encode() not in changed:
            continue
        previous = json.loads(git(objects, 'show', request['base_commit'] + ':' + manifest_path.as_posix()))
        incoming = json.loads(git(objects, 'show', head + ':' + manifest_path.as_posix()))
        require(incoming == advance_discovery(previous, after, updates), 'Candidate changed unselected discovery entries or fields')
    for name, change in updates.items():
        source = before['resources'][name]['source']
        if source['kind'] == 'submodule':
            subpath = (parent / source['path']).as_posix()
            for commit, expected in ((request['base_commit'], change['from_commit']), (head, change['to_commit'])):
                entry = git(objects, 'ls-tree', commit, '--', subpath).decode().split()
                require(entry[:3] == ['160000', 'commit', expected], 'Submodule gitlink differs from its declared pin')
    return {'schema_version': 1, 'repo': repo, 'base': base, 'branch': request['branch'], 'catalog': before['name'], 'catalog_path': path,
            'base_commit': request['base_commit'], 'generated_head': head, 'tree': git(objects, 'rev-parse', head + '^{tree}').decode().strip(), 'updates': updates}


def sync_one(state, objects, hub, *, write=False, bot='github-actions[bot]'):
    result = {'branch': state['branch'], 'remote_branch_updated': False, 'pr_updated': False, 'write_requested': write}
    push_attempted = pr_attempted = False
    try:
        remote = hub.inspect(state['branch'], state['base'])
        plan = decide(state, remote, bot); result.update(plan)
        if not write or plan['action'] in ('unchanged', 'declined'):
            result['status'] = 'preview' if not write else plan['action']; return result
        # Re-read before mutation; the explicit Git lease also checks at the push itself.
        fresh = hub.inspect(state['branch'], state['base'])
        require(all(fresh[key] == remote[key] for key in ('base_sha', 'head_sha'))
                and managed_pr(fresh['pr']) == managed_pr(remote['pr']), 'PR or branch changed during planning; nothing overwritten')
        if fresh['head_sha'] != state['generated_head']:
            push_attempted = True
            hub.push(objects, state['generated_head'], state['branch'], plan['expected_head'])
            result['remote_branch_updated'] = True
        latest = hub.inspect(state['branch'], state['base'])
        require(latest['base_sha'] == state['base_commit'], 'Default branch advanced after push; prepare a new candidate')
        require(latest['head_sha'] == state['generated_head'], 'Branch changed after push; PR text was preserved')
        if plan['pr_number']:
            require(managed_pr(latest['pr']) == managed_pr(remote['pr']),
                    'PR identity, text or state changed during publication; manual content preserved')
            pr_attempted = True
            pr = hub.update(plan['pr_number'], state)
        else:
            require(not latest['pr'] or latest['pr']['state'] == 'closed', 'A PR appeared during publication; rerun to reconcile it')
            pr_attempted = True
            pr = hub.create(state)
        result.update(status='synced', pr_updated=True, pr_number=pr['number'], pr_url=pr['html_url'])
    except (ValueError, OSError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        if push_attempted and not result['remote_branch_updated']: result['remote_branch_updated'] = None
        if pr_attempted: result['pr_updated'] = None
        result.update(status='partial' if push_attempted or pr_attempted else 'blocked', reason=str(exc))
    return result


def sync_batch(root, directory, repo, base, *, write=False, bot='github-actions[bot]', hub=None):
    root, directory = Path(root).resolve(), Path(directory).resolve()
    require(REPO.fullmatch(repo), 'Invalid repository')
    index = json.loads((directory / 'index.json').read_text())
    require(index.get('schema_version') == 1 and index.get('kind') == 'claudespace-update-batch', 'Invalid update artifact index')
    hub = hub or GitHubPRs(repo); rows = []
    for item in index['candidates']:
        try:
            bundle, receipt_path = within(directory, item['bundle']), within(directory, item['receipt'])
            require(bundle.is_file() and receipt_path.is_file() and not bundle.is_symlink() and not receipt_path.is_symlink(), 'Missing candidate artifact')
            receipt = json.loads(receipt_path.read_text())
            with tempfile.TemporaryDirectory(prefix='claudespace-pr-') as temp:
                objects = Path(temp) / 'objects.git'
                state = inspect_bundle(root, bundle, receipt, objects, repo, base)
                rows.append(sync_one(state, objects, hub, write=write, bot=bot))
        except (ValueError, OSError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as exc:
            rows.append({'status': 'blocked', 'reason': str(exc), 'remote_branch_updated': False, 'pr_updated': False})
    return {'schema_version': 1, 'kind': 'claudespace-pr-sync', 'write_requested': write, 'results': rows,
            'status': 'needs_attention' if any(row['status'] in ('blocked', 'partial') for row in rows) else 'ok', 'merged': False, 'installed': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--base', default='main')
    parser.add_argument('--bot-login', default='github-actions[bot]')
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--format', choices=('text', 'json'), default='text')
    args = parser.parse_args(argv)
    require(not args.report.exists() and not args.report.is_symlink() and not args.report.resolve().is_relative_to(args.root.resolve()), 'Use a new report outside the checkout')
    try:
        report = sync_batch(args.root, args.directory, args.repo, args.base, write=args.write, bot=args.bot_login)
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as exc:
        report = {'schema_version': 1, 'kind': 'claudespace-pr-sync', 'status': 'needs_attention',
                  'write_requested': args.write, 'results': [{'status': 'blocked', 'reason': str(exc)}]}
    write_json(args.report, report)
    if args.format == 'json':
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        labels = {'preview': '仅预览', 'synced': 'PR 已同步', 'unchanged': '候选相同，复用现有 PR',
                  'declined': '同一候选已关闭，保留这一决定', 'blocked': '已停止', 'partial': '操作未完成，需核对远端状态'}
        for row in report['results']:
            print(row.get('branch', '候选') + '：' + labels[row['status']] + ('；' + row['reason'] if row.get('reason') else ''))
            if row.get('pr_url'): print('PR：' + row['pr_url'])
        print('完整 JSON：' + str(args.report.resolve()))
    return 1 if report['status'] == 'needs_attention' else 0


if __name__ == '__main__':
    raise SystemExit(main())
