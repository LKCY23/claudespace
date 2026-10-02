#!/usr/bin/env python3
"""Render host catalogs and import unchanged, pinned skill files for local packages."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import ssl
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = ROOT / 'domains' / 'candidates'


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def download(repo, sha, path):
    request = urllib.request.Request(
        f'https://raw.githubusercontent.com/{repo}/{sha}/{path}',
        headers={'User-Agent': 'claudespace-candidate-import'})
    try:
        return urllib.request.urlopen(request, timeout=30).read()
    except urllib.error.URLError as exc:
        if not isinstance(exc.reason, ssl.SSLCertVerificationError):
            raise
        # macOS may have a system Python without the OS CA bundle. curl uses its
        # verified trust store; never disable TLS verification to import code.
        return subprocess.check_output(['curl', '--fail', '--silent', '--show-error',
                                        '--location', '--max-time', '30', request.full_url])


def import_package(item):
    root = DOMAIN / item['source'][2:]
    origin = item['upstream']
    imported = {}
    for source, target in item['imports'].items():
        data = download(origin['repo'], origin['sha'], source)
        path = root / target
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        imported[target] = {'upstream_path': source, 'sha256': hashlib.sha256(data).hexdigest()}
    revision = item.get('packaging_revision', 1)
    version = f'0.1.0+claudespace.{revision}.{origin["sha"][:12]}'
    if item['name'] == 'code-simplifier':
        target = root / 'codex/skills/code-simplifier/SKILL.md'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((ROOT / 'scripts/templates/code-simplifier-codex.md').read_text())
        manifest = json.loads((root / 'upstream/claude-plugin.json').read_text())
        manifest['version'] = version
        write_json(root / '.claude-plugin/plugin.json', manifest)
        packaging = 'Original agent rules unchanged. Codex orchestration skill dispatches one independent subagent; both hosts use a packaging revision.'
    else:
        write_json(root / '.claude-plugin/plugin.json', {
            'name': item['name'], 'version': version,
            'description': item['description'], 'author': {'name': item['author']},
            'license': 'MIT', 'skills': './skills/'})
        packaging = 'Original skills and references unchanged; only plugin manifests added.'
    write_json(root / '.codex-plugin/plugin.json', {
        'name': item['name'], 'version': version,
        'description': item['description'], 'author': {'name': item['author']},
        'skills': './codex/skills/' if item['name'] == 'code-simplifier' else './skills/'})
    write_json(root / 'UPSTREAM.json', {**origin, 'packaging_revision': revision,
                                      'packaging': packaging, 'files': imported})


def render(catalog):
    entries = [{key: item[key] for key in ('name', 'source', 'description')}
               for item in catalog['plugins']]
    write_json(DOMAIN / '.claude-plugin/marketplace.json', {
        'name': catalog['name'], 'owner': {'name': 'LKCY23'},
        'description': 'Candidates: collected for trial, not validated or installed by default.',
        'plugins': entries})
    native = [{**entry, 'category': 'Productivity',
               'policy': {'installation': 'AVAILABLE', 'authentication': 'ON_USE'}}
              for entry in entries]
    write_json(DOMAIN / '.agents/plugins/marketplace.json', {
        'name': catalog['name'],
        'interface': {'displayName': 'claudespace · Candidates (未验证)'}, 'plugins': native})


def validate(catalog):
    names = set()
    for item in catalog['plugins']:
        if item['name'] in names:
            raise ValueError('Duplicate plugin name: ' + item['name'])
        names.add(item['name'])
        if item['maturity'] != 'candidate' or item['default_install']:
            raise ValueError('Candidates must remain explicitly selected, unvalidated entries')
        sha = item['upstream']['sha']
        if len(sha) != 40 or any(c not in '0123456789abcdef' for c in sha):
            raise ValueError('Upstream must be pinned to an exact commit')
        if isinstance(item['source'], dict) and item['source'].get('sha') != sha:
            raise ValueError('Source pin differs from recorded upstream')
        if isinstance(item['source'], str):
            package = (DOMAIN / item['source']).resolve()
            if not package.is_relative_to(DOMAIN.resolve()):
                raise ValueError('Package escapes the candidate domain')
            if item.get('packaging') == 'upstream-submodule':
                actual = subprocess.check_output(['git', '-C', str(package), 'rev-parse', 'HEAD'], text=True).strip()
                if actual != sha:
                    raise ValueError('Upstream submodule pin differs: ' + item['name'])
                if subprocess.check_output(['git', '-C', str(package), 'status', '--porcelain', '--untracked-files=no'], text=True).strip():
                    raise ValueError('Upstream tracked contents changed: ' + item['name'])
                continue
            record = json.loads((package / 'UPSTREAM.json').read_text())
            if record['sha'] != sha:
                raise ValueError('Imported package pin differs from catalog')
            for relative, info in record['files'].items():
                if hashlib.sha256((package / relative).read_bytes()).hexdigest() != info['sha256']:
                    raise ValueError('Upstream file changed: ' + relative)
            if item['name'] == 'code-simplifier':
                if (package / 'codex/skills/code-simplifier/SKILL.md').read_text() != (ROOT / 'scripts/templates/code-simplifier-codex.md').read_text():
                    raise ValueError('Codex orchestration entry differs from the packaging template')
            for host in ['claude', 'codex']:
                manifest = json.loads((package / f'.{host}-plugin/plugin.json').read_text())
                expected = f'0.1.0+claudespace.{item.get("packaging_revision", 1)}.{sha[:12]}'
                if manifest['version'] != expected:
                    raise ValueError('Host packaging version mismatch: ' + item['name'])
    return len(names)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--import-upstream', action='store_true', help='Download the pinned local packages')
    parser.add_argument('--check', action='store_true', help='Validate without rewriting catalogs')
    args = parser.parse_args()
    catalog = json.loads((DOMAIN / 'catalog.json').read_text())
    if args.import_upstream:
        for item in catalog['plugins']:
            if 'imports' in item:
                import_package(item)
    count = validate(catalog)
    if not args.check:
        render(catalog)
    else:
        expected = {item['name'] for item in catalog['plugins']}
        for filename in ['.claude-plugin/marketplace.json', '.agents/plugins/marketplace.json']:
            actual = json.loads((DOMAIN / filename).read_text())
            if actual['name'] != catalog['name']:
                raise ValueError('Catalog identity drift: ' + filename)
            if {p['name'] for p in actual['plugins']} != expected:
                raise ValueError('Catalog membership drift: ' + filename)
            by_name = {p['name']: p for p in actual['plugins']}
            for item in catalog['plugins']:
                if by_name[item['name']]['source'] != item['source']:
                    raise ValueError('Catalog source drift: ' + item['name'])
                if filename.startswith('.agents/') and by_name[item['name']].get('policy') != {'installation': 'AVAILABLE', 'authentication': 'ON_USE'}:
                    raise ValueError('Candidate install policy drift: ' + item['name'])
    print(f'{count} candidate plugins: exact pins and original files verified')


if __name__ == '__main__':
    main()
