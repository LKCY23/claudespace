"""Committed source candidates are isolated from baseline and native installations."""
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
import prepare_update as module
from check_updates import check_catalog


class PrepareTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.source, self.upstream, self.output = [self.root / name for name in ('source', 'upstream', 'candidate')]
        for path, repo in [(self.source, 'owner/catalog'), (self.upstream, 'owner/upstream')]:
            path.mkdir(); self.git(path, 'init', '-q'); self.git(path, 'config', 'user.name', 'fixture')
            self.git(path, 'config', 'user.email', 'fixture@example.invalid')
            self.git(path, 'remote', 'add', 'origin', 'https://github.com/' + repo + '.git')
        self.old_content = b'---\nname: demo\ndescription: original\n---\nold\n'
        (self.upstream / 'SKILL.md').write_bytes(self.old_content)
        self.commit(self.upstream)
        self.old = self.git(self.upstream, 'rev-parse', 'HEAD')
        (self.upstream / 'SKILL.md').write_bytes(self.old_content.replace(b'old\n', b'new\n'))
        self.commit(self.upstream); self.new = self.git(self.upstream, 'rev-parse', 'HEAD')
        self.item = {'kind': 'skill', 'description': 'fixture', 'origin': {'type': 'third-party', 'author': 'fixture',
                     'upstream': {'repo': 'owner/upstream', 'commit': self.old, 'path': '.'}},
                     'maintenance': {'owner': 'upstream', 'mode': 'original'},
                     'source': {'kind': 'external', 'repo': 'owner/upstream', 'commit': self.old, 'path': '.'},
                     'compatibility': {'claude-code': {'mode': 'native', 'entry': 'SKILL.md', 'validation': {'status': 'not-evaluated'}}},
                     'requires': {}, 'update': {'strategy': 'branch', 'target': 'main'}}
        self.catalog = {'schema_version': 1, 'name': 'fixture', 'resources': {'demo': self.item}}
        self.file = self.source / 'catalog.json'

    def git(self, root, *args):
        return subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid', '-c', 'commit.gpgsign=false', '-C', str(root), *args], check=True, capture_output=True, text=True).stdout.strip()

    def commit(self, root):
        self.git(root, 'add', '--all'); self.git(root, '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture')

    def save(self):
        self.file.write_text(json.dumps(self.catalog)); self.commit(self.source)
        self.base = self.git(self.source, 'rev-parse', 'HEAD')
        self.checked = check_catalog(self.catalog, lambda repo, route: {'sha': self.new} if route.startswith('commits/') else
                                     {'status': 'ahead', 'files': [{'filename': 'SKILL.md'}]})

    def prepare(self, **kwargs):
        return module.prepare(self.source, self.file, self.checked, self.output, ['demo'],
                              prepared={'owner/upstream': self.upstream}, **kwargs)

    def test_external_update_is_committed_and_baseline_untouched(self):
        self.save(); before = self.file.read_bytes()
        report = self.prepare()
        value = json.loads((self.output / 'catalog.json').read_text())['resources']['demo']
        self.assertEqual(value['source']['commit'], self.new)
        self.assertEqual(value['origin']['upstream']['commit'], self.new)
        self.assertEqual(self.file.read_bytes(), before)
        self.assertEqual(self.git(self.source, 'rev-parse', 'HEAD'), self.base)
        self.assertEqual(self.git(self.output, 'status', '--porcelain'), '')
        self.assertEqual(self.git(self.output, 'rev-parse', 'HEAD'), report['candidate_commit'])
        self.assertEqual(self.git(self.output, 'rev-parse', 'HEAD^'), self.base)
        self.assertEqual(report['status'], 'prepared')
        self.assertFalse(report['published']); self.assertFalse(report['installed'])

    def test_repeat_is_noop_but_manual_changes_and_commits_block(self):
        self.save(); first = self.prepare(); receipt = self.output / '.git' / module.RECEIPT
        before = receipt.read_bytes(); second = self.prepare()
        self.assertEqual(second['status'], 'reused'); self.assertEqual(first['candidate_commit'], second['candidate_commit'])
        self.assertEqual(receipt.read_bytes(), before)
        marker = self.output / 'human.md'; marker.write_text('retain')
        with self.assertRaisesRegex(ValueError, 'local changes'): self.prepare()
        self.commit(self.output)
        with self.assertRaisesRegex(ValueError, 'manual commit'): self.prepare()
        self.assertEqual(marker.read_text(), 'retain')

    def test_manual_branch_and_remote_changes_stop_reuse(self):
        self.save(); report = self.prepare()
        branch = report['request']['branch']
        self.git(self.output, 'branch', '-m', 'human-reviewed')
        with self.assertRaisesRegex(ValueError, 'branch was changed'): self.prepare()
        self.git(self.output, 'branch', '-m', branch)
        self.git(self.output, 'remote', 'set-url', 'origin', 'https://github.com/another/repo')
        with self.assertRaisesRegex(ValueError, 'remote was changed'): self.prepare()

    def test_update_does_not_reuse_old_native_validation_claim(self):
        self.item['compatibility']['claude-code']['validation'] = {'status': 'passed', 'level': 'runtime', 'evidence': 'old-evidence.json'}
        self.save(); self.prepare()
        item = json.loads((self.output / 'catalog.json').read_text())['resources']['demo']
        self.assertEqual(item['compatibility']['claude-code']['validation'], {'status': 'not-evaluated'})

    def test_unselected_nested_snapshot_and_alias_sources_are_protected(self):
        self.item['source'] = {'kind': 'tracked', 'path': 'packages/demo'}
        package = self.source / 'packages/demo'; package.mkdir(parents=True)
        (package / 'SKILL.md').write_bytes(self.old_content)
        nested = package / 'nested'; nested.mkdir(); (nested / 'SKILL.md').write_bytes(self.old_content)
        other = deepcopy(self.item)
        other['source'] = {'kind': 'snapshot', 'path': 'packages/demo/nested', 'baseline': 'fixture', 'sha256': 'a'*64}
        self.catalog['resources']['other'] = other
        self.save()
        with self.assertRaisesRegex(ValueError, 'overlaps another'): self.prepare()
        self.assertFalse(self.output.exists())
        (self.source / 'alias').symlink_to('packages/demo/nested', target_is_directory=True)
        self.item['source']['path'] = 'alias'; self.save()
        with self.assertRaisesRegex(ValueError, 'overlaps another'): self.prepare()
        self.assertTrue((nested / 'SKILL.md').is_file())

    def test_stale_or_forged_report_fails_before_creating_output(self):
        self.save()
        for key, value in [('catalog_fingerprint', 'bad'), ('catalog', 'different')]:
            wrong = deepcopy(self.checked); wrong[key] = value
            with self.assertRaises(ValueError): module.prepare(self.source, self.file, wrong, self.output, ['demo'])
        for key, value in [('repo', 'different/repo'), ('current_commit', 'f'*40), ('target_commit', 'main'), ('status', 'check_failed')]:
            wrong = deepcopy(self.checked); wrong['results'][0][key] = value
            with self.assertRaises(ValueError): module.prepare(self.source, self.file, wrong, self.output, ['demo'])
        self.assertFalse(self.output.exists())

    def test_duplicate_report_rows_and_unknown_selection_rejected(self):
        self.save(); self.checked['results'].append(deepcopy(self.checked['results'][0]))
        with self.assertRaisesRegex(ValueError, 'Duplicate'): self.prepare()
        self.checked['results'].pop()
        with self.assertRaisesRegex(ValueError, 'Unknown'): module.prepare(self.source, self.file, self.checked, self.output, ['missing'])

    def test_dirty_baseline_and_hidden_index_changes_rejected(self):
        self.save(); self.file.write_text(self.file.read_text()+'\n')
        with self.assertRaisesRegex(ValueError, 'local changes'): self.prepare()
        self.git(self.source, 'checkout', '--', 'catalog.json')
        self.git(self.source, 'update-index', '--assume-unchanged', 'catalog.json')
        with self.assertRaisesRegex(ValueError, 'Hidden index'): self.prepare()

    def test_existing_directory_symlink_and_output_inside_source_preserved(self):
        self.save(); self.output.mkdir(); (self.output / 'keep').write_text('untouched')
        with self.assertRaises(ValueError): self.prepare()
        shutil.rmtree(self.output); self.output.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(ValueError): self.prepare()
        self.output.unlink()
        with self.assertRaisesRegex(ValueError, 'outside'): module.prepare(self.source, self.file, self.checked, self.source / 'out', ['demo'])

    def test_new_report_target_requires_new_directory(self):
        self.save(); first = self.prepare()
        (self.upstream / 'SKILL.md').write_bytes(self.old_content.replace(b'old', b'newer')); self.commit(self.upstream)
        self.checked['results'][0]['target_commit'] = self.git(self.upstream, 'rev-parse', 'HEAD')
        with self.assertRaisesRegex(ValueError, 'different inputs'): self.prepare()
        self.assertEqual(self.git(self.output, 'rev-parse', 'HEAD'), first['candidate_commit'])

    def test_tracked_original_updates_body_only_after_matching_old_source(self):
        self.item['source'] = {'kind': 'tracked', 'path': 'packages/demo'}
        package = self.source / 'packages/demo'; package.mkdir(parents=True)
        (package / 'SKILL.md').write_bytes(self.old_content)
        self.save(); self.prepare()
        self.assertIn('new', (self.output / 'packages/demo/SKILL.md').read_text())
        self.assertEqual((package / 'SKILL.md').read_bytes(), self.old_content)
        shutil.rmtree(self.output)
        (package / 'SKILL.md').write_bytes(b'local adaptation'); self.commit(self.source)
        with self.assertRaisesRegex(ValueError, 'manual adaptation'): self.prepare()

    def test_mapped_adapter_preserves_wrapper_and_updates_provenance(self):
        self.item['source'] = {'kind': 'tracked', 'path': 'packages/demo', 'imports': {'SKILL.md': 'SKILL.md'}}
        self.item['maintenance'] = {'owner': 'ours', 'mode': 'adapter'}
        package = self.source / 'packages/demo'; package.mkdir(parents=True)
        (package / 'SKILL.md').write_bytes(self.old_content); (package / 'wrapper.md').write_text('ours')
        record = {'repo': 'owner/upstream', 'sha': self.old, 'files': {'SKILL.md': {'sha256': hashlib.sha256(self.old_content).hexdigest(), 'upstream_path': 'SKILL.md'}}}
        (package / 'UPSTREAM.json').write_text(json.dumps(record))
        self.save(); self.prepare()
        next_package = self.output / 'packages/demo'
        self.assertEqual((next_package / 'wrapper.md').read_text(), 'ours')
        self.assertIn('new', (next_package / 'SKILL.md').read_text())
        self.assertEqual(json.loads((next_package / 'UPSTREAM.json').read_text())['sha'], self.new)
        self.assertEqual(json.loads((package / 'UPSTREAM.json').read_text())['sha'], self.old)

    def test_adapter_without_mapping_and_fork_are_explicitly_manual(self):
        for mode in ('adapter', 'fork'):
            with self.subTest(mode=mode):
                self.item['maintenance']['mode'] = mode
                self.item['source'] = {'kind': 'tracked', 'path': 'packages/demo'}
                self.save()
                with self.assertRaisesRegex(ValueError, 'Manual adaptation'): self.prepare()
                self.assertFalse(self.output.exists())

    def test_submodule_pin_is_updated_in_git_index(self):
        self.item['source'] = {'kind': 'submodule', 'repo': 'owner/upstream', 'commit': self.old, 'path': 'modules/demo'}
        (self.source / '.gitmodules').write_text('[submodule "demo"]\n path = modules/demo\n url = https://github.com/owner/upstream.git\n')
        self.git(self.source, 'update-index', '--add', '--cacheinfo', '160000,'+self.old+',modules/demo')
        (self.source / 'modules/demo').mkdir(parents=True)
        self.save(); self.prepare()
        self.assertIn(self.new, self.git(self.output, 'ls-tree', 'HEAD', '--', 'modules/demo'))
        self.assertIn(self.old, self.git(self.source, 'ls-tree', 'HEAD', '--', 'modules/demo'))

    def test_submodule_url_must_match_the_declared_fixed_source(self):
        self.item['source'] = {'kind': 'submodule', 'repo': 'owner/upstream', 'commit': self.old, 'path': 'modules/demo'}
        (self.source / '.gitmodules').write_text('[submodule "demo"]\n path = modules/demo\n url = https://github.com/other/repository.git\n')
        self.git(self.source, 'update-index', '--add', '--cacheinfo', '160000,'+self.old+',modules/demo')
        (self.source / 'modules/demo').mkdir(parents=True)
        self.save()
        with self.assertRaisesRegex(ValueError, 'Submodule URL differs'): self.prepare()
        self.assertFalse(self.output.exists())

    def test_shared_dependencies_require_explicit_group(self):
        self.item['source']['dependencies'] = ['shared']
        second = deepcopy(self.item); second['source']['dependencies'] = ['shared/helper']
        self.catalog['resources']['second'] = second; self.save()
        with self.assertRaisesRegex(ValueError, 'shared update group'): self.prepare()
        result = module.prepare(self.source, self.file, self.checked, self.output, ['demo','second'], group='shared', prepared={'owner/upstream': self.upstream})
        self.assertEqual(len(result['request']['updates']), 2)

    def test_shared_companion_with_no_local_change_advances_as_one_group(self):
        self.item['source']['dependencies'] = ['shared']
        self.catalog['resources']['second'] = deepcopy(self.item); self.save()
        for row in self.checked['results']:
            if row['resource'].startswith('second@'): row['status'] = 'no_relevant_change'
        report = module.prepare(self.source, self.file, self.checked, self.output, ['demo','second'], group='shared', prepared={'owner/upstream': self.upstream})
        self.assertEqual(set(report['request']['updates']), {'demo','second'})
        self.assertEqual(report['request']['updates']['second']['to_commit'], self.new)

    def test_source_changes_during_build_and_failed_validation_leave_no_output(self):
        self.save()
        with patch.object(module, 'build', side_effect=ValueError('synthetic validation failure')):
            with self.assertRaises(ValueError): self.prepare()
        self.assertFalse(self.output.exists()); self.assertFalse(list(self.root.glob('.claudespace-prepare-*')))
        original = module.build
        def edit(*args, **kwargs):
            report = original(*args, **kwargs); (self.source / 'manual.md').write_text('keep'); return report
        with patch.object(module, 'build', side_effect=edit):
            with self.assertRaises(ValueError): self.prepare()
        self.assertFalse(self.output.exists()); self.assertEqual((self.source/'manual.md').read_text(), 'keep')

    def test_cli_has_saved_report_and_reuses_candidate(self):
        self.save(); checked = self.root / 'checked.json'; checked.write_text(json.dumps(self.checked))
        args = [sys.executable, str(ROOT/'scripts/prepare_update.py'), '--root', str(self.source), '--catalog','catalog.json',
                '--check-report',str(checked),'--resource','demo','--source','owner/upstream='+str(self.upstream),'--output',str(self.output)]
        for expected in ('源码候选已准备', '复用已有'):
            run = subprocess.run(args,capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr); self.assertIn(expected,run.stdout); self.assertIn('完整 JSON',run.stdout)
        self.assertEqual(len(list(self.root.glob('candidate.prepare-*.json'))),2)


if __name__ == '__main__':
    unittest.main()
