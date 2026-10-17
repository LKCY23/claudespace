"""Candidate builds use temporary catalogs and Git repositories, never installations."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_candidates as builder
from candidate_sources import git_files
from resource_catalog import read_catalog


def manifest_digest(files):
    value = {name: {'sha256': hashlib.sha256(content).hexdigest(), 'executable': executable}
             for name, (content, executable) in files.items()}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


class CandidateTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.source = self.root / 'source'; self.source.mkdir()
        self.catalog = self.source / 'catalog.json'
        self.output = self.root / 'output'
        self.data = {'schema_version': 1, 'name': 'fixture', 'resources': {}}

    def resource(self, name='demo', kind='skill', content=None, entry=None):
        entry = entry or ('SKILL.md' if kind == 'skill' else 'entry.json' if kind in ('mcp', 'hook') else 'entry.md')
        content = content or ('---\nname: demo\ndescription: synthetic\n---\nbody\n' if kind == 'skill' else '{}' if entry.endswith('.json') else 'body\n')
        item = {'kind': kind, 'description': 'synthetic', 'origin': {'type': 'self', 'author': 'fixture'},
                'maintenance': {'owner': 'ours', 'mode': 'original'}, 'source': {'kind': 'tracked', 'path': name},
                'compatibility': {'claude-code': {'mode': 'native', 'entry': entry, 'validation': {'status': 'not-evaluated'}}},
                'requires': {}, 'update': {'strategy': 'manual'}}
        target = self.source / name / entry; target.parent.mkdir(parents=True, exist_ok=True); target.write_text(content)
        self.data['resources'][name] = item
        return item

    def save(self):
        self.catalog.write_text(json.dumps(self.data))

    def build(self, **kwargs):
        self.save()
        return builder.build(self.catalog, self.output, **kwargs)

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.upstream), *args], check=True, capture_output=True, text=True).stdout.strip()

    def repo(self):
        self.upstream = self.root / 'upstream'; self.upstream.mkdir()
        self.git('init', '-q'); self.git('config', 'user.name', 'Fixture'); self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('remote', 'add', 'origin', 'https://github.com/owner/upstream.git')
        (self.upstream / 'SKILL.md').write_text('---\nname: demo\ndescription: original\n---\nold\n')
        self.git('add', '.'); self.git('commit', '-qm', 'original')
        return self.git('rev-parse', 'HEAD')

    def test_all_resource_kinds_and_named_mcp_entries(self):
        for kind in ('skill', 'mcp', 'hook', 'instruction', 'rule', 'agent'):
            self.resource(kind, kind)
        item = self.resource('plugin', 'plugin', json.dumps({'name': 'plugin', 'version': '1.0', 'skills': './skills'}), '.claude-plugin/plugin.json')
        (self.source / 'plugin/skills').mkdir()
        (self.source / 'plugin/skills/entry.md').write_text('synthetic plugin skill')
        self.data['resources']['mcp']['compatibility']['claude-code']['entries'] = {'http': 'http.json'}
        (self.source / 'mcp/http.json').write_text('{}')
        result = self.build()
        self.assertEqual(len(result['resources']), 7)
        native = json.loads((self.output / '.claude-plugin/marketplace.json').read_text())
        self.assertEqual([p['name'] for p in native['plugins']], ['plugin'])
        self.assertEqual(json.loads((self.output / 'source-catalog.json').read_text()), self.data)
        self.assertFalse(result['installed']); self.assertFalse(result['published'])

    def test_source_bytes_and_existing_output_are_preserved(self):
        self.resource(); self.save(); before = (self.source / 'demo/SKILL.md').read_bytes()
        result = self.build()
        self.assertEqual((self.source / 'demo/SKILL.md').read_bytes(), before)
        marker = self.output / 'manual-edit'; marker.write_text('keep')
        with self.assertRaisesRegex(ValueError, 'already exists'): self.build()
        self.assertEqual(marker.read_text(), 'keep')
        self.assertEqual(result['native_runtime'], 'not-verified')

    def test_atomic_failure_has_no_partial_output(self):
        self.resource('first'); self.resource('broken')
        (self.source / 'broken/SKILL.md').unlink()
        with self.assertRaises(ValueError): self.build()
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob('.claudespace-build-*')))

    def test_output_created_during_build_is_preserved(self):
        self.resource()
        original = builder.validate_resource
        def race(*args):
            self.output.mkdir()
            self.target_inode = self.output.stat().st_ino
            return original(*args)
        with patch.object(builder, 'validate_resource', side_effect=race):
            with self.assertRaisesRegex(ValueError, 'appeared during'):
                self.build()
        self.assertEqual(self.output.stat().st_ino, self.target_inode)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_output_inside_source_and_historical_catalog_rejected(self):
        self.resource(); self.save()
        with self.assertRaisesRegex(ValueError, 'outside'): builder.build(self.catalog, self.source / 'generated')
        self.catalog.write_text('{"version":1,"plugins":[]}')
        with self.assertRaises(ValueError): builder.build(self.catalog, self.output)

    def test_selection_never_adds_unselected_plugins(self):
        for name in ('one', 'two'):
            item = self.resource(name, 'plugin', json.dumps({'name': name, 'version': '1'}), '.claude-plugin/plugin.json')
            item['compatibility']['codex'] = deepcopy(item['compatibility']['claude-code'])
        self.build(selected=['one'])
        native = json.loads((self.output / '.agents/plugins/marketplace.json').read_text())
        self.assertEqual([p['name'] for p in native['plugins']], ['one'])
        self.assertEqual(native['plugins'][0]['policy']['installation'], 'AVAILABLE')
        self.assertFalse((self.output / 'resources/two').exists())

    def test_missing_or_escaping_manifest_reference_blocks(self):
        self.resource('plugin', 'plugin', '{"name":"plugin","skills":"../outside"}', '.claude-plugin/plugin.json')
        with self.assertRaises(ValueError): self.build()
        self.assertFalse(self.output.exists())

    def test_local_symlink_escape_blocks_but_internal_file_link_copies_body(self):
        self.resource(); outside = self.root / 'outside'; outside.write_text('private')
        link = self.source / 'demo/ref.md'; link.symlink_to(outside)
        with self.assertRaises(ValueError): self.build()
        link.unlink(); link.symlink_to('SKILL.md')
        self.build()
        self.assertEqual((self.output / 'resources/demo/ref.md').read_bytes(), (self.source / 'demo/SKILL.md').read_bytes())

    def test_snapshot_mismatch_blocks(self):
        item = self.resource()
        item['source'] = {'kind': 'snapshot', 'path': 'demo', 'baseline': 'fixture', 'sha256': '0' * 64}
        with self.assertRaisesRegex(ValueError, 'Snapshot differs'): self.build()
        item['source']['sha256'] = manifest_digest({'SKILL.md': ((self.source / 'demo/SKILL.md').read_bytes(), False)})
        self.build()

    def test_fixed_git_objects_ignore_later_checkout_edits(self):
        commit = self.repo(); item = self.resource()
        item['source'] = {'kind': 'external', 'repo': 'owner/upstream', 'commit': commit, 'path': '.'}
        (self.upstream / 'SKILL.md').write_text('different working tree')
        self.build(prepared={'owner/upstream': self.upstream})
        self.assertIn('old', (self.output / 'resources/demo/SKILL.md').read_text())
        self.assertEqual((self.upstream / 'SKILL.md').read_text(), 'different working tree')

    def test_missing_source_wrong_origin_and_unknown_commit_block(self):
        commit = self.repo(); item = self.resource()
        item['source'] = {'kind': 'external', 'repo': 'owner/upstream', 'commit': commit, 'path': '.'}
        with self.assertRaisesRegex(ValueError, 'Prepare source'): self.build()
        self.git('remote', 'set-url', 'origin', 'https://github.com/different/repo')
        with self.assertRaisesRegex(ValueError, 'identity'): self.build(prepared={'owner/upstream': self.upstream})
        self.git('remote', 'set-url', 'origin', 'https://github.com/owner/upstream')
        item['source']['commit'] = 'f' * 40
        with self.assertRaises(ValueError): self.build(prepared={'owner/upstream': self.upstream})

    def test_submodule_source_uses_pin_without_checkout_mutation(self):
        commit = self.repo(); item = self.resource()
        item['source'] = {'kind': 'submodule', 'repo': 'owner/upstream', 'commit': commit, 'path': 'upstream'}
        self.build(prepared={'owner/upstream': self.upstream})
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_git_links_outside_selected_subtree_are_rejected(self):
        commit = self.repo()
        (self.upstream / 'skills').mkdir(); (self.upstream / 'skills/link').symlink_to('../SKILL.md')
        self.git('add', '.'); self.git('commit', '-qm', 'link')
        with self.assertRaisesRegex(ValueError, 'escapes'): git_files(self.upstream, self.git('rev-parse', 'HEAD'), 'skills')

    def import_fixture(self):
        old = self.repo(); item = self.resource()
        original = (self.upstream / 'SKILL.md').read_bytes()
        (self.source / 'demo/SKILL.md').write_bytes(original)
        record = {'repo': 'owner/upstream', 'sha': old, 'files': {'SKILL.md': {'sha256': hashlib.sha256(original).hexdigest(), 'upstream_path': 'SKILL.md'}}}
        (self.source / 'demo/UPSTREAM.json').write_text(json.dumps(record))
        (self.source / 'demo/wrapper.md').write_text('our wrapper')
        (self.upstream / 'SKILL.md').write_text('---\nname: demo\ndescription: updated\n---\nnew\n')
        self.git('add', '.'); self.git('commit', '-qm', 'new')
        item['origin']['upstream'] = {'repo': 'owner/upstream', 'commit': self.git('rev-parse', 'HEAD'), 'path': '.'}
        item['source']['imports'] = {'SKILL.md': 'SKILL.md'}
        return item

    def test_explicit_import_updates_original_files_only(self):
        self.import_fixture()
        before = (self.source / 'demo/SKILL.md').read_bytes()
        with self.assertRaisesRegex(ValueError, 'commit differs'): self.build()
        self.build(prepared={'owner/upstream': self.upstream}, import_upstream=True)
        self.assertIn('new', (self.output / 'resources/demo/SKILL.md').read_text())
        self.assertEqual((self.output / 'resources/demo/wrapper.md').read_text(), 'our wrapper')
        self.assertEqual((self.source / 'demo/SKILL.md').read_bytes(), before)

    def test_import_will_not_overwrite_local_edits_or_unproven_adaptations(self):
        self.import_fixture(); (self.source / 'demo/SKILL.md').write_text('local edit')
        with self.assertRaisesRegex(ValueError, 'locally modified'): self.build(prepared={'owner/upstream': self.upstream}, import_upstream=True)
        (self.source / 'demo/UPSTREAM.json').unlink()
        with self.assertRaisesRegex(ValueError, 'recorded original'): self.build(prepared={'owner/upstream': self.upstream}, import_upstream=True)

    def test_simplifier_manifest_updates_upstream_fields_and_protects_local_changes(self):
        original = json.dumps({'name': 'code-simplifier', 'version': '1', 'description': 'old'}).encode()
        published = json.dumps({'name': 'code-simplifier', 'version': 'wrapper', 'description': 'old'}).encode()
        incoming = json.dumps({'name': 'code-simplifier', 'version': '2', 'description': 'new'}).encode()
        key = 'plugins/code-simplifier/.claude-plugin/plugin.json'
        record = {'repo': 'owner/upstream', 'sha': 'a'*40, 'files': {'upstream/claude-plugin.json': {'sha256': hashlib.sha256(original).hexdigest(), 'upstream_path': key}}}
        files = {'upstream/claude-plugin.json': (original, False), '.claude-plugin/plugin.json': (published, False),
                 '.codex-plugin/plugin.json': (b'{"name":"code-simplifier","version":"wrapper"}', False),
                 'UPSTREAM.json': (json.dumps(record).encode(), False)}
        item = {'source': {'imports': {key: 'upstream/claude-plugin.json'}}, 'origin': {'upstream': {'repo': 'owner/upstream', 'commit': 'b'*40, 'path': '.'}}}
        from unittest.mock import Mock
        sources = Mock(); sources.files.return_value = {'plugin.json': (incoming, False)}; sources.is_file.return_value = True
        result = builder.refresh_imports(deepcopy(files), item, sources)
        self.assertEqual(json.loads(result['.claude-plugin/plugin.json'][0])['description'], 'new')
        self.assertEqual(result['.codex-plugin/plugin.json'], files['.codex-plugin/plugin.json'])
        files['.claude-plugin/plugin.json'] = (b'{"name":"code-simplifier","description":"custom"}', False)
        with self.assertRaisesRegex(ValueError, 'local adaptations'): builder.refresh_imports(files, item, sources)

    def test_cli_report_and_failure_are_readable_and_never_publish(self):
        self.resource(); self.save()
        command = [sys.executable, str(ROOT / 'scripts/build_candidates.py'), '--catalog', str(self.catalog), '--output', str(self.output)]
        run = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        report = self.root / 'output.report.json'
        self.assertIn(str(report), run.stdout)
        self.assertFalse(json.loads(report.read_text())['published'])
        second = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(json.loads(report.read_text())['status'], 'ok')

    def test_cli_refuses_to_save_report_inside_source(self):
        self.resource(); self.save()
        report = self.source / 'unwanted-report.json'
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/build_candidates.py'), '--catalog', str(self.catalog),
                                 '--output', str(self.output), '--report', str(report)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(report.exists())
        self.assertFalse(self.output.exists())

    def test_cyclic_local_link_returns_blocked_json_report(self):
        self.resource(); self.save()
        (self.source / 'demo/cycle').symlink_to('cycle')
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/build_candidates.py'), '--catalog', str(self.catalog),
                                 '--output', str(self.output), '--format', 'json'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['status'], 'blocked')
        self.assertTrue(Path(report['report_path']).is_file())
        self.assertFalse(self.output.exists())


class RepositoryCatalogTests(unittest.TestCase):
    def test_every_current_catalog_is_new_format(self):
        paths = [ROOT / 'catalog.json', *(ROOT / 'domains').glob('*/catalog.json')]
        registered = [read_catalog(p) for p in paths]
        self.assertTrue(registered)
        self.assertEqual(len({item['name'] for item in registered}), len(registered))
        self.assertTrue(all(item['resources'] for item in registered))

    def test_candidate_discovery_manifests_match_new_registry(self):
        root = ROOT / 'domains/candidates'
        catalog = read_catalog(root / 'catalog.json')
        for host, file in [('claude-code', '.claude-plugin/marketplace.json'), ('codex', '.agents/plugins/marketplace.json')]:
            manifest = json.loads((root / file).read_text())
            expected = {name: item for name, item in catalog['resources'].items() if item['kind'] == 'plugin' and host in item['compatibility']}
            self.assertEqual(manifest['name'], catalog['name'])
            self.assertEqual({row['name'] for row in manifest['plugins']}, set(expected))
            for row in manifest['plugins']:
                self.assertEqual(row['source'], './' + expected[row['name']]['source']['path'])
                if host == 'codex': self.assertEqual(row['policy']['installation'], 'AVAILABLE')

    def test_candidate_wrappers_rebuild_without_upstream_or_native_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            report = builder.build(ROOT / 'domains/candidates/catalog.json', Path(directory) / 'result',
                                   selected=['code-review', 'code-simplifier', 'andrej-karpathy-skills'])
            self.assertEqual(len(report['resources']), 3)

    def test_patched_upstream_and_packaging_revision_drift_still_block(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / 'domains/candidates', root / 'source')
            catalog = root / 'source/catalog.json'
            data = json.loads(catalog.read_text()); data['resources']['code-review']['packaging_revision'] += 1
            catalog.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'version mismatch'):
                builder.build(catalog, root / 'result', selected=['code-review'])
            entry = root / 'source/packages/code-simplifier/agents/code-simplifier.md'
            entry.write_text(entry.read_text() + '\nlocal change')
            with self.assertRaisesRegex(ValueError, 'locally modified'):
                builder.build(catalog, root / 'result', selected=['code-simplifier'])


if __name__ == '__main__':
    unittest.main()
