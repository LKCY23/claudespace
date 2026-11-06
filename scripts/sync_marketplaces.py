#!/usr/bin/env python3
"""Generate host discovery files from indexed catalogs and publication policy."""
import argparse
from pathlib import Path, PurePosixPath

from catalog_index import filesystem_reader, json_value, load_catalogs, relative_path, repository_path
from resource_catalog import NAME, obj, require

HOST_PATHS = {'claude-code': '.claude-plugin/marketplace.json', 'codex': '.agents/plugins/marketplace.json'}
DISPLAY_FIELDS = ('category', 'defaultEnabled')


def encode(value):
    import json
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def publication_plan(read):
    catalogs = load_catalogs(read)
    config = json_value(read('marketplaces.json'))
    obj(config, ('schema_version', 'marketplaces'), ('schema_version', 'marketplaces'), 'marketplace policy')
    require(type(config['schema_version']) is int and config['schema_version'] == 1, 'Unsupported marketplace policy version')
    require(isinstance(config['marketplaces'], list), 'Marketplaces must be a list')
    resources = {name + '@' + catalog_name: (path, item)
                 for catalog_name, (path, catalog) in catalogs.items() for name, item in catalog['resources'].items()}
    outputs, identities, covered, result = set(), set(), set(), []
    for market in config['marketplaces']:
        fields = ('host', 'output', 'name', 'catalogs', 'skills', 'exclude', 'display', 'owner', 'interface', 'description')
        obj(market, fields, ('host', 'output', 'name', 'catalogs'), 'marketplace')
        host, output, name = market['host'], market['output'], market['name']
        require(host in HOST_PATHS, 'Unknown marketplace host')
        relative_path(output)
        suffix = PurePosixPath(HOST_PATHS[host]).parts
        require(PurePosixPath(output).parts[-len(suffix):] == suffix, 'Invalid host marketplace output')
        require(output not in outputs, 'Duplicate marketplace output'); outputs.add(output)
        require(isinstance(name, str) and NAME.fullmatch(name), 'Invalid marketplace name')
        require((host, name) not in identities, 'Duplicate host marketplace identity'); identities.add((host, name))
        declared = market['catalogs']
        require(isinstance(declared, list) and all(isinstance(c, str) and c in catalogs for c in declared), 'Unknown market catalog')
        require(len(set(declared)) == len(declared), 'Duplicate market catalog')
        covered.update(declared)
        if host == 'claude-code':
            obj(market.get('owner'), ('name',), ('name',), 'market owner')
            require(isinstance(market['owner']['name'], str) and market['owner']['name'], 'Invalid owner name')
            require('interface' not in market, 'Codex interface on Claude marketplace')
        else:
            obj(market.get('interface'), ('displayName',), ('displayName',), 'market interface')
            require(isinstance(market['interface']['displayName'], str), 'Invalid display name')
            require('owner' not in market, 'Claude owner on Codex marketplace')
        selected = {ref: 'native' for ref, (_, item) in resources.items()
                    if ref.split('@')[1] in declared and item['kind'] == 'plugin' and host in item['compatibility']}
        exclusions = market.get('exclude', {})
        require(isinstance(exclusions, dict), 'Exclusions must map resources to reasons')
        for ref, reason in exclusions.items():
            require(ref in selected and isinstance(reason, str) and reason.strip(), 'Invalid or stale exclusion: ' + ref)
            del selected[ref]
        skills = market.get('skills', {})
        require(isinstance(skills, dict), 'Skill publications must be a mapping')
        for ref, adapter in skills.items():
            require(ref in resources, 'Unknown published resource: ' + ref)
            _, item = resources[ref]
            require(item['kind'] == 'skill' and host in item['compatibility'], 'Skill has no declared host compatibility: ' + ref)
            require(host == 'claude-code' and adapter in ('native', 'skill'), 'Unsupported skill publication adapter')
            selected[ref] = adapter
        display = market.get('display', {})
        require(isinstance(display, dict) and set(display) <= set(selected), 'Display settings reference unpublished resources')
        rows, names = [], set()
        for ref, adapter in sorted(selected.items()):
            resource_name = ref.split('@')[0]
            require(resource_name not in names, 'Duplicate plugin name in marketplace: ' + resource_name); names.add(resource_name)
            catalog_path, item = resources[ref]
            require(item['compatibility'][host]['validation']['status'] != 'failed', 'Published resource declares failed compatibility: ' + ref)
            metadata = display.get(ref, {})
            obj(metadata, DISPLAY_FIELDS, (), 'display fields')
            if 'category' in metadata:
                require(isinstance(metadata['category'], str), 'Invalid category')
            if 'defaultEnabled' in metadata:
                require(host == 'claude-code' and type(metadata['defaultEnabled']) is bool, 'Invalid defaultEnabled')
            rows.append((ref, catalog_path, item, adapter, metadata))
        result.append((market, rows))
    require(covered == set(catalogs), 'Every indexed catalog needs a marketplace routing rule')
    return result


def render(read):
    outputs = {}
    for market, rows in publication_plan(read):
        host = market['host']
        suffix = PurePosixPath(HOST_PATHS[host]).parts
        market_root = PurePosixPath(*PurePosixPath(market['output']).parts[:-len(suffix)])
        entries = []
        for ref, catalog_path, item, adapter, metadata in rows:
            source = item['source']
            if source['kind'] == 'external':
                require(host == 'claude-code', 'External Codex publication needs an explicit supported adapter')
                native_source = {'source': 'git-subdir', 'url': 'https://github.com/' + source['repo'],
                                 'path': source['path'], 'sha': source['commit']}
            else:
                location = PurePosixPath(catalog_path).parent / source['path']
                require(location.is_relative_to(market_root), 'Local source is outside marketplace root: ' + ref)
                native_source = './' + str(location.relative_to(market_root))
            entry = {'name': ref.split('@')[0], 'description': item['description'], 'source': native_source, **metadata}
            if adapter == 'skill':
                skill = PurePosixPath(item['compatibility'][host]['entry'])
                require(skill.name == 'SKILL.md', 'Skill publication requires SKILL.md')
                entry.update(strict=False, skills=['./' if str(skill.parent) == '.' else './' + str(skill.parent)])
            if host == 'codex':
                entry.setdefault('category', 'Productivity')
                entry['policy'] = {'installation': 'AVAILABLE', 'authentication': 'ON_USE'}
            entries.append(entry)
        manifest = {key: market[key] for key in ('name', 'owner', 'interface', 'description') if key in market}
        manifest['plugins'] = sorted(entries, key=lambda entry: entry['name'])
        outputs[market['output']] = encode(manifest)
    return outputs


def validate_publication_package(item, adapter, host, package, name):
    """Run against an exact built package; never fetch or execute upstream code."""
    from build_candidates import package_reference, validate_manifest_paths
    if adapter == 'native':
        entry = item['compatibility'][host]['entry'] if item['kind'] == 'plugin' else '.claude-plugin/plugin.json'
        manifest = json_value(package_reference(package, entry).read_bytes())
        require(manifest.get('name') == name, 'Published plugin identity differs: ' + name)
        validate_manifest_paths(package, manifest)
        if item['kind'] == 'skill':
            skills = manifest.get('skills', [])
            skills = skills if isinstance(skills, list) else [skills]
            skill_dir = (package / item['compatibility'][host]['entry']).parent.resolve()
            require(any((package / p).resolve() == skill_dir for p in skills), 'Native wrapper does not expose catalog skill: ' + name)
    else:
        package_reference(package, item['compatibility'][host]['entry'])
        manifest = package / '.claude-plugin/plugin.json'
        if manifest.exists():
            value = json_value(manifest.read_bytes())
            require(value.get('name') == name, 'Skill wrapper identity differs: ' + name)
            components = ('skills', 'commands', 'agents', 'hooks', 'mcpServers', 'lspServers', 'outputStyles')
            require(not any(key in value for key in components), 'Inline skill conflicts with plugin manifest: ' + name)


def validate_built_publications(root, catalog_name, build_output, selected=None):
    for market, rows in publication_plan(filesystem_reader(root)):
        for ref, _, item, adapter, _ in rows:
            name, owner = ref.split('@')
            if owner == catalog_name and (selected is None or name in selected):
                validate_publication_package(item, adapter, market['host'], Path(build_output) / 'resources' / name, name)


def sync(root, *, write=False):
    root = Path(root).resolve()
    outputs = render(filesystem_reader(root))
    targets = {name: repository_path(root, name) for name in outputs}
    changed = [name for name, content in outputs.items() if not targets[name].exists() or targets[name].read_bytes() != content]
    if write:
        for name in changed:
            path = targets[name]; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(outputs[name])
    return changed


def check(root):
    changed = sync(root)
    require(not changed, 'Generated marketplaces differ; run scripts/sync_marketplaces.py --write: ' + ', '.join(changed))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--write', action='store_true'); mode.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    try:
        changed = sync(args.root, write=args.write)
        for path in changed:
            print(('Generated: ' if args.write else 'Out of date: ') + path)
        if not changed: print('Marketplaces are up to date.')
        return 1 if changed and not args.write else 0
    except (ValueError, OSError) as exc:
        print('Marketplace generation failed: ' + str(exc)); return 1


if __name__ == '__main__':
    raise SystemExit(main())
