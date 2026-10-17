#!/usr/bin/env python3
"""Build a separate structural release record for an exact committed catalog."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from resource_catalog import read_catalog


def git(root, *args):
    result = subprocess.run(['git', '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=/dev/null', '-C', str(root), *args],
                            capture_output=True, text=True, check=True, timeout=20)
    return result.stdout.strip()


def build_record(root, catalog_path='.'):
    root = Path(root).resolve()
    if Path(git(root, 'rev-parse', '--show-toplevel')).resolve() != root or git(root, 'status', '--porcelain', '--untracked-files=all'):
        raise ValueError('Release requires a clean exact repository root')
    relative = Path(catalog_path)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Catalog must stay inside the repository')
    file = root / relative / 'catalog.json'
    if file.is_symlink() or not file.resolve().is_relative_to(root):
        raise ValueError('Catalog identity escapes its repository')
    commit = git(root, 'rev-parse', 'HEAD')
    origin = git(root, 'remote', 'get-url', 'origin')
    match = re.fullmatch(r'(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([^/]+/[^/]+?)(?:\.git)?', origin)
    if match is None:
        raise ValueError('Release requires a declared GitHub repository identity')
    value = read_catalog(file)
    if any(item['validation']['status'] == 'failed' for resource in value['resources'].values() for item in resource['compatibility'].values()):
        raise ValueError('A failed declared compatibility cannot be published as a passing baseline')
    committed = subprocess.run(['git', '-C', str(root), 'show', commit + ':' + file.relative_to(root).as_posix()], capture_output=True, check=True).stdout
    if file.read_bytes() != committed:
        raise ValueError('Catalog bytes differ from the release commit')
    return {'schema_version': 1, 'kind': 'claudespace-baseline', 'repo': match[1], 'commit': commit,
            'catalog_path': relative.as_posix(), 'catalog_sha256': hashlib.sha256(committed).hexdigest(),
            'validation': {'status': 'passed', 'level': 'structural', 'scope': 'catalog-schema'}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--catalog-path', default='.')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    record = build_record(args.root, args.catalog_path)
    content = json.dumps(record, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        if args.output.resolve().is_relative_to(args.root.resolve()):
            raise ValueError('Release record must remain outside the commit it identifies')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content)
    else:
        print(content, end='')


if __name__ == '__main__':
    main()
