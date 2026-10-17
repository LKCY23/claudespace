#!/usr/bin/env python3
"""Check registered sources and export validated candidates for a separate PR job."""
import argparse
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile

from build_candidates import write_json
from candidate_sources import git
from check_updates import GitHub, check_catalog
from prepare_update import clean_head, prepare, share_update
from resource_catalog import read_catalog, require


def catalogs(root):
    return sorted([root / 'catalog.json', *(root / 'domains').glob('*/catalog.json')])


def groups(catalog):
    items = catalog['resources']; pending = set(items); result = []
    while pending:
        component = {min(pending)}; pending -= component
        while True:
            linked = {name for name in pending if any(share_update(items[name], items[other]) for other in component)}
            if not linked: break
            component |= linked; pending -= linked
        result.append(sorted(component))
    return result


def run(root, output, *, selected_catalog=None, api=None, prepared=None, fetch=False):
    root, output = Path(root).resolve(), Path(output).resolve()
    base = clean_head(root)
    require(not output.exists() and not output.is_relative_to(root), 'Use a new output directory outside the repository')
    available = catalogs(root)
    if selected_catalog:
        require(selected_catalog in [str(path.relative_to(root)) for path in available], 'Unknown catalog path')
        available = [root / selected_catalog]
    output.mkdir(parents=True)
    report = {'schema_version': 1, 'kind': 'claudespace-update-batch', 'base_commit': base,
              'checks': [], 'groups': [], 'candidates': [], 'published': False, 'installed': False}
    api = api or GitHub(os.environ.get('GITHUB_TOKEN'))
    for file in available:
        catalog = read_catalog(file)
        checked = check_catalog(catalog, api)
        check_path = 'checks/' + catalog['name'] + '.json'
        write_json(output / check_path, checked)
        report['checks'].append({'catalog': catalog['name'], 'counts': checked['counts'], 'report': check_path})
        rows = {row['resource'].split('@')[0]: row for row in checked['results']}
        for names in groups(catalog):
            if not any(rows[name]['status'] == 'update_available' for name in names): continue
            group = names[0] if len(names) == 1 else 'shared-' + names[0]
            key = catalog['name'] + '--' + group
            row = {'catalog': catalog['name'], 'resources': names, 'group': group}
            try:
                with tempfile.TemporaryDirectory(prefix='claudespace-update-') as directory:
                    candidate = Path(directory) / 'source'
                    receipt = prepare(root, file, checked, candidate, names, group=group, prepared=prepared, fetch=fetch)
                    bundle_path, receipt_path = 'candidates/' + key + '.bundle', 'candidates/' + key + '.json'
                    (output / 'candidates').mkdir(exist_ok=True)
                    git(candidate, 'bundle', 'create', str(output / bundle_path), '^' + base, receipt['request']['branch'])
                    receipt.pop('output', None)
                    write_json(output / receipt_path, receipt)
                    report['candidates'].append({'bundle': bundle_path, 'receipt': receipt_path})
                    row.update(status='prepared', commit=receipt['candidate_commit'])
            except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
                row.update(status='blocked', reason=str(exc))
            report['groups'].append(row)
    report['status'] = 'needs_attention' if any(row['status'] == 'blocked' for row in report['groups']) or any(row['counts']['check_failed'] for row in report['checks']) else 'ok'
    write_json(output / 'index.json', report)
    return report


def summary(report):
    lines = ['## Claudespace 更新检查', '', '已准备 ' + str(len(report['candidates'])) + ' 个候选；未推送或安装。', '']
    for row in report['checks']:
        counts = row['counts']
        lines.append('- ' + row['catalog'] + '：有更新 ' + str(counts['update_available']) + '；检查失败 ' + str(counts['check_failed']) + '；人工来源 ' + str(counts['manual']))
    for row in report['groups']:
        if row['status'] == 'blocked': lines.append('- 待处理 ' + row['catalog'] + '/' + row['group'] + '：' + row['reason'].replace('\n', ' '))
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--catalog', help='One repository-relative registered catalog; omitted means all')
    parser.add_argument('--fetch', action='store_true')
    args = parser.parse_args(argv)
    try:
        report = run(args.root, args.output, selected_catalog=args.catalog, fetch=args.fetch)
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print('更新检查未完成：' + str(exc), file=sys.stderr); return 2
    text = summary(report)
    (args.output / 'summary.md').write_text(text)
    print(text); print('完整 JSON：' + str((args.output / 'index.json').resolve()))
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            stream.write('ready=' + str(bool(report['candidates'])).lower() + '\n')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream: stream.write(text)
    return 1 if report['status'] == 'needs_attention' else 0


if __name__ == '__main__':
    raise SystemExit(main())
