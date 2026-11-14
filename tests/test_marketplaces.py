"""Catalog-to-marketplace projection and failure cases, without network or installs."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from catalog_index import catalog_paths, filesystem_reader
from sync_marketplaces import check, render, sync, validate_publication_package
from test_updates import resource


class MarketplaceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.item = resource(kind='plugin', source={'kind': 'external', 'repo': 'owner/plugin', 'commit': 'a'*40, 'path': 'release/plugin'},
                             compatibility={'claude-code': {'mode': 'native', 'entry': '.claude-plugin/plugin.json', 'validation': {'status': 'not-evaluated'}}})
        self.catalog = {'schema_version': 1, 'name': 'optional', 'resources': {'demo': self.item}}
        self.catalog_path = 'domains/optional/catalog.json'
        self.index = {'schema_version': 1, 'catalogs': [self.catalog_path]}
        self.market = {'host': 'claude-code', 'output': '.claude-plugin/marketplace.json', 'name': 'public-market',
                       'catalogs': ['optional'], 'owner': {'name': 'fixture'}}
        self.policy = {'schema_version': 1, 'marketplaces': [self.market]}
        self.save()

    def write(self, file, value):
        path = self.root / file; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def save(self):
        self.write('catalogs.json', self.index); self.write(self.catalog_path, self.catalog)
        self.write('marketplaces.json', self.policy)

    def entries(self):
        return json.loads(render(filesystem_reader(self.root))[self.market['output']])['plugins']

    def test_add_update_delete_and_cross_catalog_paths(self):
        sync(self.root, write=True); check(self.root)
        self.catalog['resources']['added'] = deepcopy(self.item)
        self.item['source']['commit'] = 'b'*40; self.save()
        self.assertEqual([e['name'] for e in self.entries()], ['added', 'demo'])
        with self.assertRaisesRegex(ValueError, 'Generated marketplaces differ'): check(self.root)
        sync(self.root, write=True)
        self.assertEqual(self.entries()[1]['source']['sha'], 'b'*40)
        del self.catalog['resources']['added']
        self.item['source'] = {'kind': 'tracked', 'path': 'packages/demo'}; self.save()
        self.assertEqual(self.entries()[0]['source'], './domains/optional/packages/demo')
        sync(self.root, write=True); self.assertEqual(len(self.entries()), 1)

    def test_check_does_not_write_and_generation_is_deterministic(self):
        result = subprocess.run([sys.executable, '-B', str(ROOT/'scripts/sync_marketplaces.py'), '--root', str(self.root), '--check'], capture_output=True)
        self.assertEqual(result.returncode, 1); self.assertFalse((self.root/self.market['output']).exists())
        sync(self.root, write=True)
        path = self.root / self.market['output']; before = path.stat().st_mtime_ns
        self.assertEqual(sync(self.root, write=True), []); self.assertEqual(path.stat().st_mtime_ns, before)
        path.write_text('{}')
        with self.assertRaises(ValueError): check(self.root)
        self.assertEqual(path.read_text(), '{}')

    def test_explicit_index_ignores_historical_snapshots(self):
        self.write('domains/infrastructure/old/catalog.json', {'version': 1, 'plugins': []})
        self.assertEqual(catalog_paths(self.root), [self.root/self.catalog_path])
        self.index['catalogs'].append(self.catalog_path); self.save()
        with self.assertRaisesRegex(ValueError, 'Duplicate catalog path'): self.entries()

    def test_missing_duplicate_and_escaping_catalogs_fail(self):
        for path in ['missing/catalog.json', '../catalog.json', '/catalog.json']:
            with self.subTest(path=path):
                self.index['catalogs'] = [path]; self.save()
                with self.assertRaises((ValueError, OSError)): self.entries()
        self.index['catalogs'] = [self.catalog_path, 'other/catalog.json']
        self.write('other/catalog.json', self.catalog); self.save()
        with self.assertRaisesRegex(ValueError, 'Duplicate catalog name'): self.entries()

    def test_unknown_fields_cannot_override_source_or_version(self):
        for field in ['source', 'version', 'sha', 'skills', 'strict']:
            with self.subTest(field=field):
                self.market['display'] = {'demo@optional': {field: 'unreviewed'}}; self.save()
                with self.assertRaisesRegex(ValueError, 'unknown fields'): self.entries()

    def test_unknown_reference_or_incompatible_skill_fails(self):
        self.market['skills'] = {'missing@optional': 'skill'}; self.save()
        with self.assertRaisesRegex(ValueError, 'Unknown published resource'): self.entries()
        self.item['kind'] = 'skill'; self.item['compatibility'] = {}
        self.market['skills'] = {'demo@optional': 'skill'}; self.save()
        with self.assertRaisesRegex(ValueError, 'host compatibility'): self.entries()

    def test_skill_wrapper_uses_catalog_subdirectory_and_keeps_resource_kind(self):
        self.item['kind'] = 'skill'; self.item['source']['path'] = 'skills/demo'
        self.item['compatibility']['claude-code']['entry'] = 'SKILL.md'
        self.market['skills'] = {'demo@optional': 'skill'}; self.save()
        entry = self.entries()[0]
        self.assertEqual(entry['source']['path'], 'skills/demo')
        self.assertEqual(entry['skills'], ['./']); self.assertFalse(entry['strict'])
        self.assertEqual(self.catalog['resources']['demo']['kind'], 'skill')

    def test_exclusions_are_explicit_and_stale_exclusions_fail(self):
        self.market['exclude'] = {'demo@optional': 'Not distributed in this market'}; self.save()
        self.assertEqual(self.entries(), [])
        del self.catalog['resources']['demo']; self.save()
        with self.assertRaisesRegex(ValueError, 'stale exclusion'): self.entries()

    def test_duplicate_output_identity_and_plugin_name_fail(self):
        self.policy['marketplaces'].append(deepcopy(self.market)); self.save()
        with self.assertRaisesRegex(ValueError, 'Duplicate marketplace output'): self.entries()
        self.policy['marketplaces'][1]['output'] = 'other/.claude-plugin/marketplace.json'; self.save()
        with self.assertRaisesRegex(ValueError, 'Duplicate host marketplace identity'): self.entries()
        self.policy['marketplaces'].pop()
        other = deepcopy(self.catalog); other['name'] = 'other'
        self.write('other/catalog.json', other)
        self.index['catalogs'].append('other/catalog.json'); self.market['catalogs'].append('other'); self.save()
        with self.assertRaisesRegex(ValueError, 'Duplicate plugin name'): self.entries()

    def test_host_filtering_and_codex_policy(self):
        self.item['source'] = {'kind': 'tracked', 'path': 'packages/demo'}
        self.item['compatibility']['codex'] = deepcopy(self.item['compatibility']['claude-code'])
        self.catalog['resources']['claude-only'] = deepcopy(self.item)
        del self.catalog['resources']['claude-only']['compatibility']['codex']
        self.market.update(host='codex', output='domains/optional/.agents/plugins/marketplace.json', interface={'displayName': 'Optional'})
        del self.market['owner']; self.save()
        entries = self.entries(); self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['source'], './packages/demo')
        self.assertEqual(entries[0]['policy'], {'installation': 'AVAILABLE', 'authentication': 'ON_USE'})

    def test_unsafe_output_and_symlink_do_not_write(self):
        self.market['output'] = '../.claude-plugin/marketplace.json'; self.save()
        with self.assertRaises(ValueError): sync(self.root, write=True)
        self.market['output'] = '.claude-plugin/marketplace.json'; self.save()
        outside = self.root / 'outside'; outside.mkdir()
        (self.root/'.claude-plugin').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'): sync(self.root, write=True)
        self.assertEqual(list(outside.iterdir()), [])

    def test_inline_skill_conflict_and_native_manifest_are_checked(self):
        package = self.root/'package'; (package/'.claude-plugin').mkdir(parents=True)
        (package/'SKILL.md').write_text('---\nname: demo\ndescription: fixture\n---\n')
        self.item['kind'] = 'skill'; self.item['compatibility']['claude-code']['entry'] = 'SKILL.md'
        manifest = package/'.claude-plugin/plugin.json'
        manifest.write_text(json.dumps({'name': 'demo', 'skills': ['./']}))
        with self.assertRaisesRegex(ValueError, 'conflicts'): validate_publication_package(self.item, 'skill', 'claude-code', package, 'demo')
        validate_publication_package(self.item, 'native', 'claude-code', package, 'demo')
        manifest.write_text(json.dumps({'name': 'other'}))
        with self.assertRaisesRegex(ValueError, 'identity'): validate_publication_package(self.item, 'native', 'claude-code', package, 'demo')


class RepositoryMarketplaceTests(unittest.TestCase):
    def test_all_owned_marketplaces_are_generated(self):
        check(ROOT)

    def test_existing_install_ids_survive_migration(self):
        entries = json.loads((ROOT/'.claude-plugin/marketplace.json').read_text())['plugins']
        expected = {
            'analyze-peer-work', 'github', 'skill-evaluator', 'research-brainstorm', 'teach',
            'research-dev-orchestrator', 'literature-review', 'read-paper', 'deep-research',
            'academic-paper', 'academic-paper-reviewer', 'academic-pipeline', 'karpathy-llm-wiki',
            'programming-practice', 'aris', 'agent-browser', 'autoresearchclaw', 'goal-authoring', 'sanctuary-translate', 'agent-led-swe'}
        self.assertTrue(expected <= {entry['name'] for entry in entries})


if __name__ == '__main__':
    unittest.main()
