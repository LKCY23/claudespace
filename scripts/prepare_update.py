#!/usr/bin/env python3
"""Turn an explicit update report into a separate, committed source candidate."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import uuid

from build_candidates import build, within, write_files, write_json
from candidate_sources import Sources, git, local_files
from resource_catalog import NAME, SHA, read_catalog, require, validate_catalog


RECEIPT = 'claudespace-update.json'


def clean_head(root):
    require(Path(git(root, 'rev-parse', '--show-toplevel').decode().strip()).resolve() == root.resolve(), 'Source must be an exact repository root')
    require(not git(root, 'status', '--porcelain', '--untracked-files=all').strip(), 'Repository has local changes; preserve them and use a reviewed clean baseline')
    flags = git(root, 'ls-files', '-v', '-z').split(b'\0')
    require(not any(row and (row[:1].islower() or row[:1] == b'S') for row in flags), 'Hidden index changes are not eligible for automatic candidate reuse')
    return git(root, 'rev-parse', 'HEAD').decode().strip()


def fingerprint(catalog):
    # Same one-catalog identity as check_updates; no tree-wide content cache.
    return hashlib.sha256(json.dumps(catalog, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def share_update(item, other):
    a, b = item['source'], other['source']
    same_link = a['kind'] == b['kind'] == 'submodule' and a['path'] == b['path']
    same_repo = item['origin'].get('upstream', a).get('repo') == other['origin'].get('upstream', b).get('repo')
    shared = any(Path(x).is_relative_to(y) or Path(y).is_relative_to(x)
                 for x in a.get('dependencies', []) for y in b.get('dependencies', []))
    return same_link or same_repo and shared


def advance_catalog(catalog, updates):
    candidate = deepcopy(catalog)
    for name, change in updates.items():
        item = candidate['resources'][name]
        source = item['source']
        if source['kind'] in ('external', 'submodule'):
            require(source['repo'] == change['repo'] and source['commit'] == change['from_commit'], 'Forked source needs manual adaptation: ' + name)
            source['commit'] = change['to_commit']
        if 'upstream' in item['origin']:
            item['origin']['upstream']['commit'] = change['to_commit']
        for compatible in item['compatibility'].values():
            compatible['validation'] = {'status': 'not-evaluated'}
    validate_catalog(candidate)
    return candidate


def selected_updates(catalog, checked, names):
    require(isinstance(checked, dict), 'Expected an upstream update-check report object')
    require(checked.get('schema_version') == 1 and checked.get('kind') == 'claudespace-update-check', 'Expected an upstream update-check report')
    require(checked.get('catalog') == catalog['name'] and checked.get('catalog_fingerprint') == fingerprint(catalog),
            'Update report is stale or belongs to another catalog; check again')
    require(names and len(names) == len(set(names)), 'Select distinct resource identifiers')
    rows = {}
    for row in checked.get('results', []):
        require(isinstance(row, dict) and isinstance(row.get('resource'), str) and row['resource'] not in rows, 'Duplicate or invalid update report entries')
        rows[row['resource']] = row
    updates, targets = {}, {}
    relevant = False
    for name in sorted(names):
        require(name in catalog['resources'], 'Unknown selected resource: ' + name)
        item = catalog['resources'][name]
        origin = item['origin'].get('upstream', item['source'])
        row = rows.get(name + '@' + catalog['name'], {})
        require(row.get('status') in ('update_available', 'no_relevant_change'), 'Selected resource has no usable update: ' + name)
        relevant = relevant or row['status'] == 'update_available'
        require(row.get('repo') == origin.get('repo') and row.get('current_commit') == origin.get('commit'), 'Reported old source differs from catalog: ' + name)
        target = row.get('target_commit')
        require(isinstance(target, str) and SHA.fullmatch(target) and target != row['current_commit'], 'Invalid target commit: ' + name)
        require(targets.setdefault(origin['repo'], target) == target, 'Prepare different versions of the same repository in separate candidates')
        require(item['maintenance']['mode'] != 'fork' and item['source']['kind'] != 'snapshot', 'Manual adaptation required for fork/snapshot: ' + name)
        require(item['source']['kind'] != 'tracked' or item['maintenance']['mode'] == 'original' or item['source'].get('imports'),
                'Manual adaptation required; no original-file import mapping: ' + name)
        updates[name] = {'repo': origin['repo'], 'from_commit': row['current_commit'], 'to_commit': target}
    require(relevant, 'The selected group has no relevant update')
    # Shared declared dependencies and a shared gitlink must move together.
    for name in updates:
        item = catalog['resources'][name]
        for other_name, other in catalog['resources'].items():
            if other_name in updates:
                continue
            require(not share_update(item, other), 'Include the shared update group explicitly: ' + other_name)
    return updates


def protect_local_sources(catalog, updates, root):
    # Resolve aliases too: a selected symlink must not mutate an unselected body.
    local = {name: within(root, item['source']['path']) for name, item in catalog['resources'].items()
             if item['source']['kind'] != 'external'}
    for name in updates:
        if name not in local:
            continue
        path = local[name]
        for other_name, other in local.items():
            if name == other_name:
                continue
            same_link = other_name in updates and path == other and catalog['resources'][name]['source']['kind'] == catalog['resources'][other_name]['source']['kind'] == 'submodule'
            require(same_link or not path.is_relative_to(other) and not other.is_relative_to(path),
                    'Source replacement overlaps another local resource; adapt explicitly: ' + name + ', ' + other_name)


def advance_discovery(manifest, catalog, changed):
    """Change selected source references while preserving all other entries."""
    manifest = deepcopy(manifest)
    if manifest.get('name') != catalog['name']:
        return manifest
    for entry in manifest.get('plugins', []):
        if entry.get('name') not in changed:
            continue
        source = catalog['resources'][entry['name']]['source']
        if source['kind'] == 'external':
            old = entry.get('source', {})
            require(isinstance(old, dict) and old.get('source') == 'git-subdir'
                    and old.get('url', '').removesuffix('.git') == 'https://github.com/' + source['repo'],
                    'Native external-source encoding needs manual adaptation')
            entry['source'] = {**old, 'sha': source['commit'], 'path': source['path']}
        else:
            entry['source'] = './' + source['path']
    return manifest


def update_discovery(catalog_root, catalog, changed):
    """Update existing discovery entries owned by this catalog, preserving extras."""
    for filename in ('.claude-plugin/marketplace.json', '.agents/plugins/marketplace.json'):
        path = catalog_root / filename
        if not path.exists():
            continue
        manifest = json.loads(path.read_text())
        if manifest.get('name') == catalog['name']:
            write_json(path, advance_discovery(manifest, catalog, changed))


def prepare(root, catalog_file, checked, output, names, *, group=None, prepared=None, fetch=False):
    root = Path(root).resolve()
    catalog_file = Path(catalog_file).resolve()
    require(catalog_file.is_relative_to(root), 'Catalog must be inside the source repository')
    relative = catalog_file.relative_to(root).as_posix()
    base = clean_head(root)
    require(git(root, 'show', base + ':' + relative) == catalog_file.read_bytes(), 'Catalog differs from its committed baseline')
    catalog = read_catalog(catalog_file)
    updates = selected_updates(catalog, checked, names)
    protect_local_sources(catalog, updates, catalog_file.parent)
    require(group is not None or len(updates) == 1, 'Multiple resources need --group to name the update candidate')
    group = group or next(iter(updates))
    require(isinstance(group, str) and NAME.fullmatch(group), 'Invalid update group')
    branch = 'claudespace/update/' + catalog['name'] + '/' + group
    git(root, 'check-ref-format', '--branch', branch)
    remote = git(root, 'remote', 'get-url', 'origin').decode().strip()
    require(re.fullmatch(r'(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', remote),
            'Baseline must have a GitHub repository identity without embedded credentials')
    output = Path(output).expanduser().absolute()
    require(not output.is_symlink(), 'Candidate output cannot be a symlink')
    output = output.resolve()
    require(not output.is_relative_to(root), 'Candidate must be outside the source repository')
    request = {'base_commit': base, 'base_repository': remote, 'catalog_path': relative,
               'catalog_fingerprint': fingerprint(catalog), 'branch': branch, 'updates': updates}
    if output.exists():
        require((output / '.git').is_dir() and not (output / '.git').is_symlink(), 'Existing candidate is not an owned standalone Git checkout')
        receipt_file = output / '.git' / RECEIPT
        require(receipt_file.is_file() and not receipt_file.is_symlink(), 'Existing directory has no candidate receipt; it was preserved')
        receipt = json.loads(receipt_file.read_text())
        head = clean_head(output)
        require(head == receipt.get('candidate_commit'), 'Candidate has a new manual commit; automatic handling stopped')
        require(git(output, 'symbolic-ref', '--short', 'HEAD').decode().strip() == branch,
                'Candidate branch was changed manually; it was preserved')
        require(git(output, 'remote', 'get-url', 'origin').decode().strip() == remote,
                'Candidate remote was changed manually; it was preserved')
        require(receipt.get('request') == request, 'Existing candidate has different inputs; choose a new output directory')
        return {**receipt, 'status': 'reused', 'output': str(output), 'published': False, 'installed': False}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.claudespace-prepare-', dir=output.parent) as temp:
        workspace = Path(temp)
        candidate = workspace / 'source'
        git(root, 'clone', '--quiet', '--no-hardlinks', '--no-checkout', str(root), str(candidate))
        git(candidate, 'checkout', '--quiet', '-b', branch, base)
        git(candidate, 'remote', 'set-url', 'origin', remote)
        sources = Sources(workspace / 'upstreams', prepared, fetch)
        next_catalog = advance_catalog(catalog, updates)
        direct_sources = dict(prepared or {})
        catalog_root = candidate / Path(relative).parent
        imports = []
        for name, change in updates.items():
            item = next_catalog['resources'][name]
            original = catalog['resources'][name]
            source = item['source']
            old_origin = original['origin'].get('upstream', original['source'])
            upstream = sources.repository(change['repo'], change['to_commit'])
            direct_sources[change['repo']] = upstream
            if source['kind'] == 'submodule':
                subpath = str(Path(relative).parent / source['path'])
                row = git(root, 'ls-tree', base, '--', subpath).decode().split()
                require(row[:3] == ['160000', 'commit', change['from_commit']], 'Submodule gitlink differs from its declared old pin')
                paths = [entry.decode().split('\n', 1) for entry in git(root, 'config', '--file', '.gitmodules', '--null', '--get-regexp', r'^submodule\..*\.path$').split(b'\0') if entry]
                keys = [key for key, value in paths if value == subpath]
                require(len(keys) == 1, 'Submodule path has no unique .gitmodules declaration')
                url = git(root, 'config', '--file', '.gitmodules', '--get', keys[0][:-5] + '.url').decode().strip().removesuffix('.git')
                require(url in ('https://github.com/' + change['repo'], 'git@github.com:' + change['repo'], 'ssh://git@github.com/' + change['repo']),
                        'Submodule URL differs from the catalog source; adapt it explicitly')
                git(candidate, 'update-index', '--cacheinfo', '160000,' + change['to_commit'] + ',' + subpath)
            elif source['kind'] == 'tracked':
                package = within(catalog_root, source['path'])
                require(not (candidate / relative).is_relative_to(package), 'Resource replacement would contain its own catalog')
                if source.get('imports'):
                    recorded = json.loads((package / 'UPSTREAM.json').read_text())
                    require(recorded.get('sha') == change['from_commit'] and recorded.get('repo') == change['repo'],
                            'Recorded original source differs from the reported old pin: ' + name)
                    imports.append(name)
                else:
                    old = sources.files(change['repo'], change['from_commit'], old_origin['path'])
                    require(local_files(package) == old, 'Local source differs from the old upstream; manual adaptation required: ' + name)
                    incoming = sources.files(change['repo'], change['to_commit'], old_origin['path'])
                    require(package.is_dir() and not package.is_symlink(), 'Automatic source replacement requires a real package directory')
                    shutil.rmtree(package); package.mkdir()
                    write_files(package, incoming)
        validate_catalog(next_catalog)
        next_file = candidate / relative
        write_json(next_file, next_catalog)
        built = build(next_file, workspace / 'build', prepared=direct_sources, selected=sorted(updates), import_upstream=bool(imports))
        for name in imports:
            package = within(catalog_root, next_catalog['resources'][name]['source']['path'])
            require(package.is_dir() and not package.is_symlink(), 'Import target must be a real package directory')
            shutil.rmtree(package)
            shutil.copytree(workspace / 'build/resources' / name, package)
        update_discovery(catalog_root, next_catalog, updates)
        # Stage only the candidate checkout. Its hooks are disabled for every Git command.
        git(candidate, 'add', '--all')
        git(candidate, '-c', 'commit.gpgsign=false', '-c', 'user.name=Claudespace Updates',
            '-c', 'user.email=claudespace-updates@users.noreply.github.com', 'commit', '--quiet', '-m',
            'Update ' + group + ' in ' + catalog['name'])
        head = clean_head(candidate)
        changed_files = git(candidate, 'diff', '--name-only', base, head).decode().splitlines()
        receipt = {'schema_version': 1, 'kind': 'claudespace-source-candidate', 'status': 'prepared',
                   'request': request, 'candidate_commit': head, 'output': str(output), 'changed_files': changed_files,
                   'checks': built['resources'], 'published': False, 'installed': False, 'native_runtime': 'not-verified'}
        write_json(candidate / '.git' / RECEIPT, receipt)
        require(clean_head(root) == base, 'Source baseline changed during preparation; nothing published')
        require(not output.exists() and not output.is_symlink(), 'Output appeared during preparation; it was preserved')
        candidate.rename(output)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--catalog', type=Path, required=True, help='Path inside --root, relative to it or absolute')
    parser.add_argument('--check-report', type=Path, required=True)
    parser.add_argument('--resource', action='append', required=True)
    parser.add_argument('--group')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', action='append', default=[], metavar='OWNER/REPO=DIR')
    parser.add_argument('--fetch', action='store_true')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--format', choices=('text', 'json'), default='text')
    args = parser.parse_args(argv)
    report_path = (args.report or args.output.with_name(args.output.name + '.prepare-' + uuid.uuid4().hex[:8] + '.json')).absolute()
    allowed = False
    try:
        require(not report_path.exists() and not report_path.is_symlink(), 'Report already exists; choose a new file')
        require(not report_path.resolve().is_relative_to(args.root.resolve()) and not report_path.resolve().is_relative_to(args.output.resolve()),
                'Report must stay outside the source and candidate Git repositories')
        report_path = report_path.resolve(); allowed = True
        prepared = {}
        for value in args.source:
            repo, separator, directory = value.partition('=')
            require(separator and repo and directory and repo not in prepared, 'Use distinct --source OWNER/REPO=DIR arguments')
            prepared[repo] = Path(directory)
        catalog_file = args.catalog if args.catalog.is_absolute() else args.root / args.catalog
        checked = json.loads(args.check_report.read_text())
        report = prepare(args.root, catalog_file, checked, args.output, args.resource,
                         group=args.group, prepared=prepared, fetch=args.fetch)
        code = 0
    except (ValueError, OSError, UnicodeError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as exc:
        report = {'schema_version': 1, 'kind': 'claudespace-source-candidate', 'status': 'blocked',
                  'reason': str(exc), 'published': False, 'installed': False}
        code = 1
    try:
        require(allowed, 'Report path is unavailable')
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open('x') as stream:
            report['report_path'] = str(report_path)
            json.dump(report, stream, ensure_ascii=False, indent=2); stream.write('\n')
    except (OSError, ValueError):
        report.pop('report_path', None)
        report['report_error'] = 'Could not save a new report; existing files were preserved'; code = 2
    if args.format == 'json':
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        if report['status'] == 'blocked':
            print('源码候选准备已停止：' + report['reason'])
        else:
            print('复用已有源码候选；未改写。' if report['status'] == 'reused' else '源码候选已准备并通过结构检查。')
            print('目录：' + report['output']); print('分支：' + report['request']['branch'])
            print('未推送、发布或安装；实际运行尚未验证。')
        if 'report_path' in report: print('完整 JSON：' + report['report_path'])
        if 'report_error' in report: print(report['report_error'])
    return code


if __name__ == '__main__':
    raise SystemExit(main())
