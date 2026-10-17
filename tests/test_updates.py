from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from check_updates import CheckError, check_catalog
from resource_catalog import read_catalog, validate_catalog

OLD, NEW = 'a' * 40, 'b' * 40


def resource(**changes):
    item = {'kind': 'skill', 'description': 'Test resource',
            'origin': {'type': 'third-party', 'author': 'Upstream',
                       'upstream': {'repo': 'owner/repo', 'commit': OLD, 'path': 'skills/selected'}},
            'maintenance': {'owner': 'ours', 'mode': 'adapter'},
            'source': {'kind': 'tracked', 'path': 'packages/selected'},
            'compatibility': {'codex': {'mode': 'original', 'entry': 'SKILL.md',
                                      'validation': {'status': 'not-evaluated'}}},
            'requires': {}, 'update': {'strategy': 'branch', 'target': 'main'}}
    item.update(changes)
    return item


def catalog(**entries):
    return {'schema_version': 1, 'name': 'test', 'resources': entries or {'one': resource()}}


class FakeAPI:
    def __init__(self, files=None, commit=NEW, error=None, status='ahead'):
        self.files = [{'filename': 'skills/selected/SKILL.md'}] if files is None else files
        self.commit, self.error, self.status = commit, error, status
        self.calls = []

    def __call__(self, repo, route):
        self.calls.append((repo, route))
        if self.error:
            raise self.error
        if route.startswith('commits/'):
            return {'sha': self.commit}
        if route.startswith('compare/'):
            return {'status': self.status, 'files': self.files}
        if route.startswith('releases/'):
            return {'tag_name': 'v2', 'draft': False, 'prerelease': False}
        raise AssertionError('Unexpected API route')


class CatalogTests(unittest.TestCase):
    def test_named_mcp_entries_are_closed_and_package_relative(self):
        item = resource(kind='mcp')
        host = item['compatibility']['codex']
        host.update(entry='stdio.json', entries={'stdio': 'stdio.json', 'http': 'http.json'})
        validate_catalog(catalog(one=item))
        host['entries']['http'] = '../outside.json'
        with self.assertRaises(ValueError):
            validate_catalog(catalog(one=item))

    def test_named_entries_do_not_expand_other_resource_kinds(self):
        item = resource()
        item['compatibility']['codex']['entries'] = {'other': 'SKILL.md'}
        with self.assertRaises(ValueError):
            validate_catalog(catalog(one=item))

    def test_strict_new_catalog_and_old_format_rejected(self):
        validate_catalog(catalog())
        for value in ({'version': 1, 'name': 'old', 'plugins': []}, catalog(one=resource(extra=True)),
                      {'schema_version': True, 'name': 'bad', 'resources': {}}):
            with self.assertRaises(ValueError):
                validate_catalog(value)

    def test_fixed_pin_and_tracking_target_required(self):
        for change in ({'update': {'strategy': 'branch'}}, {'update': {'strategy': 'latest'}},
                       {'origin': {'type': 'third-party', 'author': 'author',
                                   'upstream': {'repo': 'owner/repo', 'commit': 'main', 'path': '.'}}}):
            with self.assertRaises(ValueError):
                validate_catalog(catalog(one=resource(**change)))

    def test_validation_claim_needs_level_and_evidence(self):
        item = resource()
        item['compatibility']['codex']['validation'] = {'status': 'passed'}
        with self.assertRaises(ValueError):
            validate_catalog(catalog(one=item))

    def test_snapshot_requires_hash_and_manual_strategy(self):
        item = resource(origin={'type': 'third-party', 'author': 'vendor', 'baseline': '1.0'},
                        source={'kind': 'snapshot', 'path': 'snapshot', 'baseline': '1.0', 'sha256': 'a' * 64},
                        update={'strategy': 'manual'})
        validate_catalog(catalog(one=item))
        item['source']['sha256'] = 'invalid'
        with self.assertRaises(ValueError):
            validate_catalog(catalog(one=item))

    def test_path_traversal_and_resource_binding_schema(self):
        item = resource()
        item['source']['path'] = '../outside'
        with self.assertRaises(ValueError):
            validate_catalog(catalog(one=item))
        item = resource(requires={'bindings': {'token': {'kind': 'secret', 'required': True}}})
        validate_catalog(catalog(one=item))
        item['requires']['bindings']['token']['value'] = 'password'
        with self.assertRaises(ValueError):
            validate_catalog(catalog(one=item))

    def test_duplicate_json_keys_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'catalog.json'
            file.write_text('{"schema_version":1,"schema_version":1,"name":"x","resources":{}}')
            with self.assertRaises(ValueError):
                read_catalog(file)


class UpdateTests(unittest.TestCase):
    def row(self, data=None, api=None):
        return check_catalog(data or catalog(), api or FakeAPI())['results'][0]

    def test_changed_resource_reports_candidate_and_keeps_input(self):
        data = catalog()
        before = deepcopy(data)
        row = self.row(data)
        self.assertEqual(row['status'], 'update_available')
        self.assertEqual(row['current_commit'], OLD)
        self.assertEqual(row['target_commit'], NEW)
        self.assertTrue(row['adaptation_required'])
        self.assertEqual(data, before)

    def test_unrelated_paths_do_not_create_candidate(self):
        row = self.row(api=FakeAPI(files=[{'filename': 'skills/selected-other/SKILL.md'}]))
        self.assertEqual(row['status'], 'no_relevant_change')

    def test_imports_shared_dependencies_and_renames_are_compared(self):
        item = resource()
        item['source']['imports'] = {'LICENSE': 'LICENSE'}
        item['source']['dependencies'] = ['shared/helper']
        for file in ({'filename': 'LICENSE'}, {'filename': 'shared/helper/run.sh'},
                     {'filename': 'other/new.md', 'previous_filename': 'skills/selected/old.md'}):
            self.assertEqual(self.row(catalog(one=item), FakeAPI(files=[file]))['status'], 'update_available')

    def test_normalize_dot_paths(self):
        item = resource()
        item['origin']['upstream']['path'] = './skills/selected/'
        self.assertEqual(self.row(catalog(one=item))['status'], 'update_available')

    def test_matching_pin_does_not_request_comparison(self):
        api = FakeAPI(commit=OLD)
        self.assertEqual(self.row(api=api)['status'], 'no_change')
        self.assertEqual(len(api.calls), 1)

    def test_shared_query_and_failures_are_deduplicated(self):
        data = catalog(one=resource(), two=resource())
        for api in (FakeAPI(), FakeAPI(error=CheckError('GitHub HTTP 403'))):
            report = check_catalog(data, api)
            self.assertEqual(len(api.calls), 2 if api.error is None else 1)
            self.assertEqual(len(report['results']), 2)

    def test_network_failure_not_up_to_date_or_secret_log(self):
        report = check_catalog(catalog(), FakeAPI(error=RuntimeError('private-token-in-error')))
        self.assertEqual(report['counts']['check_failed'], 1)
        self.assertNotIn('private-token', json.dumps(report))

    def test_manual_resource_does_not_query_remote(self):
        api = FakeAPI()
        self.assertEqual(self.row(catalog(one=resource(update={'strategy': 'manual'})), api)['status'], 'manual')
        self.assertEqual(api.calls, [])

    def test_full_file_limit_and_rewound_branch_block(self):
        files = [{'filename': 'file' + str(index)} for index in range(300)]
        for api in (FakeAPI(files=files), FakeAPI(status='behind'), FakeAPI(status='diverged')):
            self.assertEqual(self.row(api=api)['status'], 'check_failed')

    def test_capped_comparison_uses_complete_trees_and_both_rename_paths(self):
        item = resource()
        base = FakeAPI(files=[{'filename': 'unrelated/' + str(i)} for i in range(300)])
        def entry(path, sha, mode='100644', kind='blob'):
            return {'path': path, 'sha': sha, 'mode': mode, 'type': kind}
        trees = {OLD: [entry('skills/selected/old.md', OLD), entry('same', OLD), entry('mode-only', OLD)],
                 NEW: [entry('elsewhere/new.md', OLD), entry('same', OLD), entry('mode-only', OLD, '100755'),
                       entry('executable', NEW, '100755')]}
        def api(repo, route):
            if route.startswith('git/trees/'):
                return {'truncated': False, 'tree': trees[route.split('/')[2].split('?')[0]]}
            return base(repo, route)
        row = self.row(catalog(one=item), api)
        self.assertEqual(row['status'], 'update_available')
        self.assertEqual(row['changed_files'], ['skills/selected/old.md'])
        self.assertEqual(row['comparison_method'], 'complete_git_trees')
        item['origin']['upstream']['path'] = '.'
        row = self.row(catalog(one=item), api)
        self.assertEqual(row['changed_files'], ['elsewhere/new.md', 'executable', 'mode-only', 'skills/selected/old.md'])
        item['origin']['upstream']['path'] = 'same'
        self.assertEqual(self.row(catalog(one=item), api)['status'], 'no_relevant_change')

    def test_capped_comparison_rejects_incomplete_or_malformed_trees(self):
        base = FakeAPI(files=[{'filename': str(i)} for i in range(300)])
        for tree in ({'truncated': True, 'tree': []}, {'tree': []},
                     {'truncated': False, 'tree': [{'path': 'file', 'type': 'blob', 'mode': '100644', 'sha': 'bad'}]}):
            with self.subTest(tree=tree):
                def api(repo, route):
                    return tree if route.startswith('git/trees/') else base(repo, route)
                self.assertEqual(self.row(api=api)['status'], 'check_failed')

    def test_release_resolves_tag_to_commit_not_target_commitish(self):
        api = FakeAPI()
        row = self.row(catalog(one=resource(update={'strategy': 'release', 'target': 'latest'})), api)
        self.assertEqual(row['target_commit'], NEW)
        self.assertIn(('owner/repo', 'releases/latest'), api.calls)
        self.assertIn(('owner/repo', 'commits/v2'), api.calls)

    def test_validate_entire_catalog_before_first_query(self):
        api = FakeAPI()
        with self.assertRaises(ValueError):
            check_catalog(catalog(one=resource(), two=resource(extra=True)), api)
        self.assertEqual(api.calls, [])

    def test_bad_sha_and_missing_diff_are_failed_checks(self):
        self.assertEqual(self.row(api=FakeAPI(commit='main'))['status'], 'check_failed')
        self.assertEqual(self.row(api=FakeAPI(files='bad'))['status'], 'check_failed')


if __name__ == '__main__':
    unittest.main()
