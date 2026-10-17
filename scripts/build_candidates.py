#!/usr/bin/env python3
"""Build an isolated, structurally checked candidate from a new resource catalog."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

from candidate_sources import Sources, local_files
from resource_catalog import read_catalog, require

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def within(root, relative):
    path = (root / relative).resolve()
    require(path.is_relative_to(root.resolve()), 'Path escapes the declared package: ' + relative)
    return path


def package_reference(package, relative):
    path = within(package, relative)
    require(path.exists(), 'Missing package reference: ' + relative)
    return path


def validate_manifest_paths(package, manifest):
    for field in ('skills', 'agents', 'hooks'):
        values = manifest.get(field, [])
        # Inline hook definitions are valid and remain with the resource body.
        if field == 'hooks' and isinstance(values, dict):
            continue
        for relative in values if isinstance(values, list) else [values]:
            require(isinstance(relative, str), 'Manifest component must be a package path: ' + field)
            package_reference(package, relative)


def validate_simplifier_entry(package, manifest):
    roots = manifest.get('skills', [])
    roots = roots if isinstance(roots, list) else [roots]
    entries = [package_reference(package, root) / 'code-simplifier/SKILL.md' for root in roots]
    entries = [entry for entry in entries if entry.is_file()]
    require(len(entries) == 1, 'Codex manifest must expose one Code Simplifier entry')
    skill = entries[0]
    require(skill.resolve().is_relative_to(package.resolve()), 'Exported entry escapes its package')
    refs = re.findall(r'`([^`\n]*agents/code-simplifier\.md)`', skill.read_text())
    require(len(refs) == 1, 'Code Simplifier entry must reference its original rule file')
    target = package_reference(package, str(skill.parent.relative_to(package) / refs[0]))
    require(target == package_reference(package, 'agents/code-simplifier.md'), 'Simplifier resolves a different rule file')


def verify_record(files, item, *, changing_pin=False):
    if 'UPSTREAM.json' not in files:
        return None
    record = json.loads(files['UPSTREAM.json'][0])
    upstream = item['origin'].get('upstream')
    require(upstream is not None and record['repo'] == upstream['repo'], 'Package provenance repository differs from catalog')
    require(changing_pin or record['sha'] == upstream['commit'], 'Package provenance commit differs from catalog; prepare an explicit import')
    for name, info in record.get('files', {}).items():
        digest = info['sha256'] if isinstance(info, dict) else info
        require(name in files and hashlib.sha256(files[name][0]).hexdigest() == digest,
                'Imported file was locally modified or removed: ' + name)
    return record


def refresh_imports(files, item, sources):
    imports = item['source'].get('imports', {})
    require(imports, 'This resource has no explicit import mapping; adapt its source separately')
    record = verify_record(files, item, changing_pin=True)
    require(record is not None, 'Import needs a recorded original-file baseline; local adaptations require review')
    if 'upstream/claude-plugin.json' in files and item['source']['imports'].get('plugins/code-simplifier/.claude-plugin/plugin.json'):
        native = json.loads(files['.claude-plugin/plugin.json'][0])
        original = json.loads(files['upstream/claude-plugin.json'][0])
        require({k: v for k, v in native.items() if k != 'version'} == {k: v for k, v in original.items() if k != 'version'},
                'Claude manifest has local adaptations; review them before updating its upstream definition')
    upstream = item['origin']['upstream']
    imported = {}
    for source, target in imports.items():
        incoming = sources.files(upstream['repo'], upstream['commit'], source)
        # Existing mappings may select a directory or a single file.
        single = sources.is_file(upstream['repo'], upstream['commit'], source)
        for name, content in incoming.items():
            destination = target if single else str(Path(target) / name)
            require(destination not in imported, 'Import mappings overlap: ' + destination)
            old = record.get('files', {}).get(destination)
            require(old is not None or destination not in files, 'Import would overwrite a local adaptation: ' + destination)
            files[destination] = content
            imported[destination] = {'upstream_path': source if single else str(Path(source) / name),
                                     'sha256': hashlib.sha256(content[0]).hexdigest()}
    # Retire only previously recorded imported files, never local wrappers.
    for name in record.get('files', {}):
        if name not in imported:
            files.pop(name, None)
    record.update(sha=upstream['commit'], path=upstream['path'], files=imported)
    files['UPSTREAM.json'] = ((json.dumps(record, indent=2, ensure_ascii=False) + '\n').encode(), False)
    if 'plugins/code-simplifier/.claude-plugin/plugin.json' in imports:
        files['.claude-plugin/plugin.json'] = files['upstream/claude-plugin.json']
    return files


def write_files(directory, files):
    for relative, (content, executable) in sorted(files.items()):
        path = within(directory, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        path.chmod(0o755 if executable else 0o644)


def validate_resource(name, item, package):
    checks = []
    for host, compatible in sorted(item['compatibility'].items()):
        entries = [compatible['entry'], *compatible.get('entries', {}).values()]
        for relative in entries:
            entry = package_reference(package, relative)
            require(entry.is_file(), 'Native entry is not a file: ' + relative)
            if item['kind'] == 'plugin':
                manifest = json.loads(entry.read_text())
                require(manifest.get('name') == name, 'Plugin identity differs from catalog: ' + name)
                validate_manifest_paths(package, manifest)
                if name == 'code-simplifier' and host == 'codex':
                    validate_simplifier_entry(package, manifest)
            elif entry.suffix == '.json':
                json.loads(entry.read_text())
            elif item['kind'] == 'skill':
                text = entry.read_text()
                require(text.startswith('---\n') and '\n---' in text[4:], 'Skill entry has no YAML frontmatter: ' + name)
        evidence = compatible['validation']
        if evidence['status'] != 'not-evaluated':
            package_reference(package, evidence['evidence'])
        require(evidence['status'] != 'failed', 'Resource declares a failed compatibility: ' + name + '/' + host)
        checks.append({'agent': host, 'status': 'passed', 'level': 'structural',
                       'note': 'Entry and package references checked; native loading and runtime not exercised'})
    return checks


def render(catalog, selected):
    manifests = {}
    for host, filename in [('claude-code', '.claude-plugin/marketplace.json'), ('codex', '.agents/plugins/marketplace.json')]:
        entries = [{'name': name, 'description': catalog['resources'][name]['description'], 'source': './resources/' + name}
                   for name in selected if catalog['resources'][name]['kind'] == 'plugin'
                   and host in catalog['resources'][name]['compatibility']]
        if host == 'codex':
            entries = [{**entry, 'category': 'Productivity', 'policy': {'installation': 'AVAILABLE', 'authentication': 'ON_USE'}} for entry in entries]
            manifests[filename] = {'name': catalog['name'], 'interface': {'displayName': catalog['name'] + ' · candidates'}, 'plugins': entries}
        else:
            manifests[filename] = {'name': catalog['name'], 'owner': {'name': 'LKCY23'}, 'plugins': entries}
    return manifests


def build(catalog_file, output, *, prepared=None, fetch=False, selected=None, import_upstream=False):
    catalog_file, output = Path(catalog_file).resolve(), Path(output).expanduser().absolute()
    catalog = read_catalog(catalog_file)
    names = sorted(selected or catalog['resources'])
    require(names and len(set(names)) == len(names) and all(name in catalog['resources'] for name in names), 'Select existing distinct resource identifiers')
    require(not output.exists() and not output.is_symlink(), 'Output already exists; choose a new candidate directory')
    output = output.resolve()
    require(not output.resolve().is_relative_to(catalog_file.parent), 'Candidate output must be outside the source catalog directory')
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {'schema_version': 1, 'kind': 'claudespace-candidate-build', 'catalog': catalog['name'],
              'source_catalog': str(catalog_file), 'output': str(output), 'status': 'ok', 'resources': [],
              'published': False, 'installed': False, 'native_runtime': 'not-verified'}
    with tempfile.TemporaryDirectory(prefix='.claudespace-build-', dir=output.parent) as temp:
        workspace = Path(temp)
        stage = workspace / 'candidate'; stage.mkdir()
        sources = Sources(workspace / 'upstreams', prepared, fetch)
        for name in names:
            item = catalog['resources'][name]
            source = item['source']
            if source['kind'] in ('external', 'submodule'):
                local = within(catalog_file.parent, source['path']) if source['kind'] == 'submodule' else None
                files = sources.files(source['repo'], source['commit'], '.' if local else source['path'], local)
            else:
                files = local_files(within(catalog_file.parent, source['path']))
            if source['kind'] == 'snapshot':
                manifest = {path: {'sha256': hashlib.sha256(content).hexdigest(), 'executable': mode} for path, (content, mode) in files.items()}
                digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
                require(digest == source['sha256'], 'Snapshot differs from its declared baseline: ' + name)
            if import_upstream and source.get('imports'):
                files = refresh_imports(files, item, sources)
            else:
                verify_record(files, item)
            package = stage / 'resources' / name; package.mkdir(parents=True)
            write_files(package, files)
            if import_upstream and name in ('code-simplifier', 'code-review') and source.get('imports'):
                version = '0.1.0+claudespace.' + str(item.get('packaging_revision', 1)) + '.' + item['origin']['upstream']['commit'][:12]
                for compatible in item['compatibility'].values():
                    file = package / compatible['entry']
                    manifest = json.loads(file.read_text()); manifest['version'] = version
                    write_json(file, manifest)
            if name in ('code-simplifier', 'code-review') and source.get('imports'):
                expected = '0.1.0+claudespace.' + str(item.get('packaging_revision', 1)) + '.' + item['origin']['upstream']['commit'][:12]
                for compatible in item['compatibility'].values():
                    require(json.loads((package / compatible['entry']).read_text()).get('version') == expected,
                            'Host packaging version mismatch: ' + name)
            checks = validate_resource(name, item, package)
            report['resources'].append({'resource': name + '@' + catalog['name'], 'kind': item['kind'],
                                        'source': deepcopy(source), 'files': len(files), 'checks': checks})
        write_json(stage / 'source-catalog.json', catalog)
        for filename, manifest in render(catalog, names).items():
            write_json(stage / filename, manifest)
        # Output is a build artifact, not a published catalog or a Profile selection.
        require(not output.exists() and not output.is_symlink(), 'Output appeared during the build; it was preserved')
        stage.rename(output)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', action='append', default=[], metavar='OWNER/REPO=DIR')
    parser.add_argument('--fetch', action='store_true', help='Fetch only declared fixed commits into a temporary build directory')
    parser.add_argument('--resource', action='append', help='Explicit resource identifier; default: all entries')
    parser.add_argument('--import-upstream', action='store_true', help='Refresh explicitly mapped original files in the candidate only')
    parser.add_argument('--report', type=Path, help='JSON report path; default: OUTPUT.report.json')
    parser.add_argument('--format', choices=('text', 'json'), default='text')
    args = parser.parse_args(argv)
    report_path = (args.report or args.output.with_name(args.output.name + '.report.json')).absolute()
    report_allowed = False
    try:
        require(not report_path.exists() and not report_path.is_symlink(), 'Report already exists; choose a new report path')
        require(not report_path.resolve().is_relative_to(args.catalog.resolve().parent), 'Report must be outside the source catalog directory')
        report_path = report_path.resolve()
        report_allowed = True
        prepared = {}
        for value in args.source:
            repo, separator, directory = value.partition('=')
            require(separator and repo and directory and repo not in prepared, 'Use distinct --source OWNER/REPO=DIR arguments')
            prepared[repo] = Path(directory)
        report = build(args.catalog, args.output, prepared=prepared, fetch=args.fetch, selected=args.resource, import_upstream=args.import_upstream)
        code = 0
    except (ValueError, OSError, UnicodeError, subprocess.SubprocessError, KeyError, TypeError, RuntimeError) as exc:
        report = {'schema_version': 1, 'kind': 'claudespace-candidate-build', 'status': 'blocked',
                  'reason': str(exc), 'published': False, 'installed': False}
        code = 1
    try:
        require(report_allowed, 'Report path is unavailable')
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open('x') as stream:
            report['report_path'] = str(report_path)
            json.dump(report, stream, indent=2, ensure_ascii=False); stream.write('\n')
    except (OSError, ValueError):
        report.pop('report_path', None)
        report['report_error'] = 'Could not save a new report; an existing report was preserved'
        code = 2
    if args.format == 'json':
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print('候选构建完成：' + str(len(report['resources'])) + ' 项资源。' if report['status'] == 'ok' else '候选构建已停止：' + report['reason'])
        if report['status'] == 'ok':
            print('输出：' + report['output']); print('已检查包内容与入口；原生加载、实际运行尚未验证。')
        if 'report_path' in report:
            print('完整 JSON：' + report['report_path'])
        if report.get('report_error'):
            print(report['report_error'])
    return code


if __name__ == '__main__':
    raise SystemExit(main())
