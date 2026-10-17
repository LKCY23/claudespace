#!/usr/bin/env python3
"""Read allowlisted private sources with deploy keys; publish metadata-only results."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from urllib.parse import unquote

from build_candidates import write_json
from candidate_sources import git
from check_updates import CheckError, GitHub
from prepare_update import clean_head
from resource_catalog import REPO, read_catalog, require
import run_updates
from validate_catalogs import validate

TRUSTED_ROOT = Path(__file__).resolve().parents[1]


def policy():
    value = json.loads((TRUSTED_ROOT / 'ci/private-sources.json').read_text())
    require(value.get('schema_version') == 1 and isinstance(value.get('repositories'), dict), 'Invalid private source policy')
    for repo, entry in value['repositories'].items():
        require(REPO.fullmatch(repo) and set(entry) == {'key_env'}
                and re.fullmatch(r'CLAUDESPACE_[A-Z0-9_]+', entry['key_env']), 'Invalid private source identity')
    return value['repositories']


def private_items(root, rules, selected_catalog=None):
    paths = run_updates.catalogs(root)
    if selected_catalog:
        require(selected_catalog in [p.relative_to(root).as_posix() for p in paths], 'Unknown catalog path')
        paths = [root / selected_catalog]
    result = []
    for path in paths:
        require(not path.is_symlink() and path.resolve().is_relative_to(root.resolve()),
                'Catalog must stay inside the inspected repository')
        for item in read_catalog(path)['resources'].values():
            source = item['source']; origin = item['origin'].get('upstream', source)
            private_repo = source.get('repo') if source.get('repo') in rules else origin.get('repo')
            if private_repo not in rules:
                continue
            require(source['kind'] == 'external' and source['repo'] == private_repo
                    and origin.get('repo') == private_repo and item['maintenance']['mode'] == 'original',
                    'Private bodies must remain external; automatic public imports are not allowed')
            result.append(item)
    return result


def take_keys(rules):
    """Remove all allowlisted secrets before any child process, even for public-only work."""
    return {repo: os.environ.pop(entry['key_env'], '') for repo, entry in rules.items()}


@contextmanager
def private_sources(root, rules, *, tracking=False, selected_catalog=None, tolerate_errors=False, keys=None):
    """Prepared repositories and key files live only inside this context."""
    keys = take_keys(rules) if keys is None else keys
    items = private_items(root, rules, selected_catalog)
    with tempfile.TemporaryDirectory(prefix='claudespace-private-') as directory:
        workspace = Path(directory); prepared, targets = {}, {}
        for repo in sorted({item['source']['repo'] for item in items}):
            try:
                key_value = keys.pop(repo, '')
                require(key_value.startswith('-----BEGIN OPENSSH PRIVATE KEY-----'), 'Configured private source key is missing or invalid')
                key_file = workspace / (repo.replace('/', '--') + '.key')
                with os.fdopen(os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
                    stream.write(key_value.rstrip() + '\n')
                key_value = None
                checkout = workspace / repo.replace('/', '--'); checkout.mkdir()
                git(checkout, 'init', '--quiet')
                git(checkout, 'remote', 'add', 'origin', 'https://github.com/' + repo + '.git')
                ssh = shlex.join(['ssh', '-F', '/dev/null', '-p', '443', '-o', 'Hostname=ssh.github.com',
                                 '-o', 'HostKeyAlias=github.com', '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
                                 '-o', 'IdentityAgent=none', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=20',
                                 '-o', 'GlobalKnownHostsFile=/dev/null', '-o', 'UserKnownHostsFile=' + str(TRUSTED_ROOT / 'ci/github-known-hosts'),
                                 '-i', str(key_file)])
                def fetch(ref):
                    git(checkout, '-c', 'core.sshCommand=' + ssh, 'fetch', '--quiet', '--no-tags', 'git@github.com:' + repo + '.git', ref)
                    return git(checkout, 'rev-parse', 'FETCH_HEAD').decode().strip()
                selected = [item for item in items if item['source']['repo'] == repo]
                if tracking:
                    for item in selected:
                        update = item['update']
                        require(update['strategy'] in ('branch', 'manual'), 'Private Git tracking supports branch or manual updates')
                        if update['strategy'] == 'branch' and (repo, update['target']) not in targets:
                            ref = 'refs/heads/' + update['target']
                            git(checkout, 'check-ref-format', ref)
                            targets[repo, update['target']] = fetch(ref)
                for pin in sorted({item['source']['commit'] for item in selected}):
                    try:
                        present = git(checkout, 'rev-parse', '--verify', pin + '^{commit}').decode().strip() == pin
                    except ValueError:
                        present = False
                    if not present:
                        require(fetch(pin) == pin, 'Private source resolved to a different fixed commit')
                prepared[repo] = checkout
            except (ValueError, OSError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError):
                if not tolerate_errors:
                    raise
                # The API reports this allowlisted repository as unavailable;
                # unrelated public update groups can still be prepared.
                continue
        yield prepared, targets


class SourceAPI:
    """Private branch comparison uses Git; public queries retain the existing API."""
    def __init__(self, prepared, targets, public, private_repos=None):
        self.prepared, self.targets, self.public = prepared, targets, public
        self.private_repos = set(prepared if private_repos is None else private_repos)

    def __call__(self, repo, route):
        if repo not in self.private_repos:
            return self.public(repo, route)
        if repo not in self.prepared:
            raise CheckError('Private source access failed; check its configured read-only key and fixed commits')
        if route.startswith('commits/'):
            target = self.targets.get((repo, unquote(route.removeprefix('commits/'))))
            if target:
                return {'sha': target}
            raise CheckError('Private tracking target is not configured')
        match = re.fullmatch(r'compare/([0-9a-f]{40})\.\.\.([0-9a-f]{40})\?per_page=100&page=1', route)
        if not match:
            raise CheckError('Private Git query is unsupported')
        before, after = match.groups(); checkout = self.prepared[repo]
        common = git(checkout, 'merge-base', before, after).decode().strip()
        state = 'ahead' if common == before else 'behind' if common == after else 'diverged'
        files = git(checkout, 'diff', '--name-only', '--no-renames', '-z', before, after).split(b'\0')
        return {'status': state, 'files': [{'filename': path.decode()} for path in files if path]}


def validate_sources(root, report_file, rules, *, keys=None):
    keys = take_keys(rules) if keys is None else keys
    root, report_file = root.resolve(), report_file.resolve()
    require(not report_file.exists() and not report_file.is_relative_to(root), 'Use a new report outside the source checkout')
    result = {'schema_version': 1, 'kind': 'claudespace-private-source-validation', 'status': 'failed',
              'native_runtime': 'not-verified', 'private_bodies_published': False}
    try:
        result['commit'] = clean_head(root)
        with private_sources(root, rules, keys=keys) as (prepared, _), tempfile.TemporaryDirectory(prefix='claudespace-validation-') as directory:
            output = Path(directory) / 'build'
            built = validate(root, output, prepared=prepared, fetch=True)
            result.update(status=built['status'], catalogs=built['catalogs'], private_repositories=sorted(prepared))
            result['resource_count'] = sum(len(json.loads(path.read_text()).get('resources', [])) for path in output.glob('*.json'))
        require(clean_head(root) == result['commit'], 'Source changed during validation')
    except (ValueError, OSError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError):
        # Reports and logs are public. Never echo private source contents or exception data.
        result.update(status='failed', reason='Private access or resource validation failed; check the configured read-only key, fixed commits and resource declarations')
    write_json(report_file, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('validate', 'prepare'))
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--catalog')
    args = parser.parse_args(argv)
    rules = policy()
    keys = take_keys(rules)
    if args.operation == 'validate':
        if not args.report:
            parser.error('--report is required')
        result = validate_sources(args.root, args.report, rules, keys=keys)
        text = '固定来源验证：' + ('通过' if result['status'] == 'passed' else '未通过') + '\n完整 JSON：' + str(args.report.resolve())
        print(text)
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream: stream.write(text + '\n')
        return 0 if result['status'] == 'passed' else 1
    if not args.output:
        parser.error('--output is required')
    output_allowed = False
    try:
        require(not args.output.exists() and not args.output.is_symlink()
                and not args.output.resolve().is_relative_to(args.root.resolve()), 'Use a new output outside the checkout')
        base = clean_head(args.root.resolve())
        output_allowed = True
        with private_sources(args.root.resolve(), rules, tracking=True, selected_catalog=args.catalog, tolerate_errors=True, keys=keys) as (prepared, targets):
            report = run_updates.run(args.root, args.output, selected_catalog=args.catalog, prepared=prepared, fetch=True,
                                     private_repos=rules, api=SourceAPI(prepared, targets, GitHub(os.environ.get('GITHUB_TOKEN')), rules))
        return run_updates.emit(report, args.output)
    except (ValueError, OSError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError):
        print('更新候选未准备完成：请检查私有来源密钥、固定提交和分支配置。')
        if output_allowed and not args.output.exists():
            report = {'schema_version': 1, 'kind': 'claudespace-update-batch', 'base_commit': base,
                      'checks': [], 'groups': [{'catalog': args.catalog or 'private-sources', 'group': 'private-access',
                                               'status': 'blocked', 'reason': 'Private source access or tracking setup failed'}],
                      'candidates': [], 'status': 'needs_attention', 'published': False, 'installed': False}
            write_json(args.output / 'index.json', report)
            return run_updates.emit(report, args.output)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
