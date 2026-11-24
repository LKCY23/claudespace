"""Active-resource filtering tests using temporary profiles and mocked SSH/Git."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import active_resources as module
import check_updates
import private_ci
import run_updates
import test_prepare_update as fixtures
from test_updates import FakeAPI, catalog, resource

KEY = '-----BEGIN OPENSSH PRIVATE KEY-----\nTEST-ACTIVE-PROFILE-KEY\n-----END OPENSSH PRIVATE KEY-----\n'
NEW = 'b' * 40


class ActiveResourceTests(unittest.TestCase):
    def write_profile_repo(self, root):
        (root / 'machines').mkdir(parents=True, exist_ok=True)
        (root / 'profiles/agents/claude-code').mkdir(parents=True, exist_ok=True)
        (root / 'profiles/agents/antigravity').mkdir(parents=True, exist_ok=True)
        (root / 'profiles/apps/codex-app').mkdir(parents=True, exist_ok=True)
        (root / 'machines/workstation.yaml').write_text(
            "schema_version: 1\nmachine_id: workstation\nagents:\n"
            "  claude-code: profiles/agents/claude-code/main.yaml\n"
            "apps:\n"
            "  codex-app: profiles/apps/codex-app/current.yaml\n"
        )
        (root / 'machines/mini.yaml').write_text(
            "schema_version: 1\nmachine_id: mini\nagents:\n"
            "  claude-code: profiles/agents/claude-code/third.yaml\n"
            "  antigravity: profiles/agents/antigravity/official.yaml\n"
        )
        (root / 'profiles/agents/claude-code/main.yaml').write_text(
            "schema_version: 1\nagent_type: claude-code\nresources:\n  plugins:\n"
            "    active-plugin@test: {}\n"
            "    enabled-somewhere@test:\n      options:\n        enabled: false\n"
            "  skills:\n    disabled-everywhere@test:\n      options:\n        control:\n          enabled: false\n"
        )
        (root / 'profiles/agents/claude-code/third.yaml').write_text(
            "schema_version: 1\nagent_type: claude-code\nresources:\n  plugins:\n"
            "    enabled-somewhere@test:\n      options:\n        enabled: true\n"
            "  skills:\n    disabled-everywhere@test:\n      options:\n        control:\n          enabled: false\n"
        )
        (root / 'profiles/agents/antigravity/official.yaml').write_text(
            "schema_version: 1\nagent_type: antigravity\nresources:\n  plugins:\n"
            "    folio@claudespace-personal:\n      options:\n        enabled: true\n"
        )
        (root / 'profiles/apps/codex-app/current.yaml').write_text(
            "schema_version: 1\napp: codex-app\nsettings:\n  localeOverride: en-US\n"
        )

    def test_parse_simple_yaml_matches_pyyaml_across_real_constructs(self):
        samples = [
            (
                "# comment header\nschema_version: 1\nflag: true\nnil: ~\n"
                "empty_str: ''\ncolon_val: 'https://example.com:8443/a#b'\n"
                "quoted: \"line1\\nline2\"\nfloats: -12.5\nversion_str: 0.8.0\n"
                "inline_map: {enabled: false, nested: {k: 'v,1'}}\n"
                "inline_list: [one, 'two', 3]\n"
                "bindings:\n  /settings/statusLine/command:\n    kind: command\n"
                "    args:\n    - resource: claude-hud@claudespace-external\n      path: dist/index.js\n"
                "    - literal-arg\n"
            ),
            "empty_obj: {}\nonly_key:\nnext_key: null\n",
        ]
        for sample in samples:
            self.assertEqual(module.parse_simple_yaml(sample), yaml.safe_load(sample))

    def test_parse_simple_yaml_rejects_tabs_anchors_and_tags(self):
        for bad in ("\tkey: val\n", "a: &anchor 1\n", "a: *alias\n", "a: !custom 1\n"):
            with self.assertRaises(ValueError):
                module.parse_simple_yaml(bad)

    def test_collect_active_resources_unions_machines_including_antigravity_and_excludes_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_profile_repo(root)
            active = module.collect_active_resources(root)
            self.assertEqual(active, frozenset({
                'active-plugin@test',
                'enabled-somewhere@test',
                'folio@claudespace-personal',
            }))
            self.assertNotIn('disabled-everywhere@test', active)

    def test_collect_active_resources_rejects_profile_traversal_and_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_profile_repo(root)
            outside = root.parent / 'outside.yaml'
            outside.write_text('schema_version: 1\nresources: {}\n')
            (root / 'machines/bad.yaml').write_text('schema_version: 1\nagents:\n  claude-code: ../outside.yaml\n')
            with self.assertRaises(ValueError):
                module.collect_active_resources(root)
            (root / 'machines/bad.yaml').unlink()
            (root / 'profiles/agents/antigravity/official.yaml').unlink()
            (root / 'profiles/agents/antigravity/official.yaml').symlink_to(outside)
            with self.assertRaises(ValueError):
                module.collect_active_resources(root)

    def test_expand_active_dependencies_and_share_update_components(self):
        dep_cat = {
            'schema_version': 1,
            'name': 'deps',
            'resources': {
                'helper': resource(),
            },
        }
        main_item = resource(requires={'resources': ['helper@deps']})
        shared_active = resource(
            origin={'type': 'third-party', 'author': 'Upstream', 'upstream': {'repo': 'owner/shared', 'commit': 'a' * 40, 'path': 'skills/a'}},
            source={'kind': 'submodule', 'repo': 'owner/shared', 'commit': 'a' * 40, 'path': 'domains/upstreams/shared'},
        )
        shared_sibling = deepcopy(shared_active)
        shared_sibling['origin']['upstream']['path'] = 'skills/b'
        shared_manual = deepcopy(shared_active)
        shared_manual['update'] = {'strategy': 'manual'}
        unused = resource()
        main_cat = {
            'schema_version': 1,
            'name': 'main',
            'resources': {
                'primary': main_item,
                'shared_active': shared_active,
                'shared_sibling': shared_sibling,
                'shared_manual': shared_manual,
                'unused': unused,
            },
        }
        expanded = module.expand_active_dependencies({'deps': dep_cat, 'main': main_cat}, {'primary@main', 'shared_active@main'})
        self.assertEqual(expanded, frozenset({'primary@main', 'helper@deps', 'shared_active@main'}))
        names = module.active_catalog_names(main_cat, expanded)
        self.assertEqual(names, frozenset({'primary', 'shared_active', 'shared_sibling'}))
        self.assertNotIn('shared_manual', names)
        self.assertNotIn('unused', names)

    def test_check_catalog_skips_api_for_inactive_and_keeps_unfiltered_schema(self):
        data = catalog(
            active=resource(),
            unused=resource(),
            retired=resource(update={'strategy': 'manual'}),
        )
        unfiltered_api = FakeAPI()
        unfiltered = check_updates.check_catalog(data, unfiltered_api)
        self.assertNotIn('inactive', unfiltered['counts'])

        filtered_api = FakeAPI()
        filtered = check_updates.check_catalog(data, filtered_api, active_refs={'active@test'})
        rows = {row['resource']: row for row in filtered['results']}
        self.assertEqual(rows['active@test']['status'], 'update_available')
        self.assertEqual(rows['unused@test']['status'], 'inactive')
        self.assertEqual(rows['retired@test']['status'], 'manual')
        self.assertEqual(filtered['counts']['inactive'], 1)
        self.assertEqual(len(filtered_api.calls), 2)

        only_unused_api = FakeAPI()
        only_unused = check_updates.check_catalog(catalog(unused=resource()), only_unused_api, active_refs={'other@test'})
        self.assertEqual(only_unused['results'][0]['status'], 'inactive')
        self.assertEqual(only_unused_api.calls, [])

    def test_private_ci_active_filter_pops_secret_and_fails_closed_without_key(self):
        f = fixtures.PrepareTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        f.save()
        output = f.root / 'batch-missing-key'
        with patch.dict(os.environ, {'CLAUDESPACE_CONFIG_DATA_KEY': ''}, clear=False):
            code = private_ci.main(['prepare', '--root', str(f.source), '--output', str(output), '--active-filter'])
            self.assertNotIn('CLAUDESPACE_CONFIG_DATA_KEY', os.environ)
        self.assertEqual(code, 1)
        index = json.loads((output / 'index.json').read_text())
        self.assertEqual(index['status'], 'needs_attention')
        self.assertNotIn(KEY, json.dumps(index))

    def test_private_ci_active_filter_end_to_end_with_mocked_ssh(self):
        f = fixtures.PrepareTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        f.item['update']['target'] = f.git(f.upstream, 'branch', '--show-current')
        # Add an unused external resource whose GitHub API must never be called when filtered.
        unused_item = resource()
        unused_item['origin']['upstream']['repo'] = 'owner/unused-external'
        f.catalog['resources']['unused_external'] = unused_item
        f.save()

        # Build a separate profile git repository containing a synthetic active ref matching fixture demo@fixture.
        profile_upstream = f.root / 'config-data-upstream'
        profile_upstream.mkdir()
        f.git(profile_upstream, 'init', '--quiet')
        f.git(profile_upstream, 'config', 'user.email', 'test@example.com')
        f.git(profile_upstream, 'config', 'user.name', 'Test')
        (profile_upstream / 'machines').mkdir()
        (profile_upstream / 'profiles/agents/antigravity').mkdir(parents=True)
        (profile_upstream / 'machines/secret-host-mini.yaml').write_text(
            'schema_version: 1\nmachine_id: secret-host-mini\nagents:\n  antigravity: profiles/agents/antigravity/official.yaml\n'
        )
        (profile_upstream / 'profiles/agents/antigravity/official.yaml').write_text(
            'schema_version: 1\nagent_type: antigravity\nresources:\n  plugins:\n    demo@fixture: {}\n'
        )
        f.git(profile_upstream, 'add', '.')
        f.git(profile_upstream, 'commit', '-q', '-m', 'profiles')
        profile_branch = f.git(profile_upstream, 'branch', '--show-current')

        real_git = private_ci.git
        seen_keys = []
        def mock_git(root, *args, **kwargs):
            if 'fetch' in args:
                config = next(arg for arg in args if arg.startswith('core.sshCommand='))
                command = shlex.split(config.split('=', 1)[1])
                key_path = Path(command[command.index('-i') + 1])
                seen_keys.append(key_path)
                self.assertEqual(key_path.stat().st_mode & 0o777, 0o600)
                self.assertNotIn('CLAUDESPACE_CONFIG_DATA_KEY', os.environ)
                self.assertNotIn('CLAUDESPACE_TEST_KEY', os.environ)
                upstream_dir = profile_upstream if 'claude-config-data' in args[-2] else f.upstream
                return real_git(root, 'fetch', '--quiet', '--no-tags', str(upstream_dir), args[-1])
            return real_git(root, *args, **kwargs)

        rules = {'owner/upstream': {'key_env': 'CLAUDESPACE_TEST_KEY'}}
        profile_policy = {'schema_version': 1, 'repository': 'LKCY23/claude-config-data',
                          'ref': profile_branch, 'key_env': 'CLAUDESPACE_CONFIG_DATA_KEY'}
        output = f.root / 'batch-active'
        with (patch.object(private_ci, 'policy', return_value=rules),
              patch.object(private_ci, 'active_profile_policy', return_value=profile_policy),
              patch.object(private_ci, 'git', side_effect=mock_git),
              patch.object(private_ci, 'GitHub', return_value=unittest.mock.Mock(side_effect=AssertionError('Inactive external API must not be called'))),
              patch.dict(os.environ, {'CLAUDESPACE_TEST_KEY': KEY, 'CLAUDESPACE_CONFIG_DATA_KEY': KEY})):
            code = private_ci.main(['prepare', '--root', str(f.source), '--output', str(output), '--active-filter'])
            self.assertNotIn('CLAUDESPACE_CONFIG_DATA_KEY', os.environ)

        self.assertEqual(code, 0)
        self.assertTrue(all(not p.exists() for p in seen_keys))
        index = json.loads((output / 'index.json').read_text())
        self.assertEqual(index['active_filter'], {'enabled': True, 'active_resource_count': 1})
        self.assertEqual(index['checks'][0]['counts']['inactive'], 1)
        checked = json.loads((output / 'checks/fixture.json').read_text())
        statuses = {row['resource']: row['status'] for row in checked['results']}
        self.assertEqual(statuses, {'demo@fixture': 'update_available', 'unused_external@fixture': 'inactive'})
        all_bytes = b'\n'.join(p.read_bytes() for p in output.rglob('*') if p.is_file())
        self.assertNotIn(b'secret-host-mini', all_bytes)
        self.assertNotIn(KEY.encode(), all_bytes)
        self.assertIn('未启用跳过 1', (output / 'summary.md').read_text())

    def test_resource_updates_workflow_security_and_default_active_filter(self):
        workflow_text = (ROOT / '.github/workflows/resource-updates.yml').read_text()
        workflow = yaml.load(workflow_text, Loader=yaml.BaseLoader)
        self.assertNotIn('pip install', workflow_text)
        inputs = workflow['on']['workflow_dispatch']['inputs']
        self.assertEqual(inputs['all_resources']['default'], 'false')

        prepare_job = workflow['jobs']['prepare']
        step = next(s for s in prepare_job['steps'] if 'private_ci.py' in s.get('run', ''))
        self.assertEqual(step['env']['CLAUDESPACE_CONFIG_DATA_KEY'], '${{ secrets.CLAUDESPACE_CONFIG_DATA_KEY }}')
        self.assertIn('--active-filter', step['run'])
        self.assertIn('ALL_RESOURCES', step['run'])

        pull_requests_job = workflow['jobs']['pull_requests']
        self.assertNotIn('CLAUDESPACE_CONFIG_DATA_KEY', str(pull_requests_job))


if __name__ == '__main__':
    unittest.main()
