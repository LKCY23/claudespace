from copy import deepcopy
import unittest
from run_updates import update_groups, upstream_group
from sync_update_prs import same_scope, decide
from test_github_updates import state, pr_for


def catalog():
    return {'resources': {name: {'origin': {'upstream': {'repo': 'larksuite/cli'}},
        'source': {'kind': 'tracked', 'path': name}, 'update': {'strategy': 'branch', 'target': 'main'}}
        for name in ['apps', 'doc', 'retired', 'current']}}


def checked():
    return {'results': [{'resource': n+'@test', 'status': s, 'repo': 'larksuite/cli', 'target_commit': 'b'*40}
        for n, s in [('apps', 'update_available'), ('doc', 'update_available'), ('retired', 'manual'), ('current', 'no_change')]]}


class BatchTests(unittest.TestCase):
    def test_same_upstream_and_target_are_one_batch_without_retired_or_current(self):
        value = catalog(); value['resources']['retired']['update'] = {'strategy': 'manual'}
        self.assertEqual(update_groups(value, checked()), [(upstream_group('larksuite/cli'), ['apps', 'doc'])])

    def test_different_targets_and_sources_are_not_combined(self):
        report = checked(); report['results'][1]['target_commit'] = 'c'*40
        self.assertEqual(update_groups(catalog(), report), [('apps', ['apps']), ('doc', ['doc'])])
        report = checked(); report['results'][1]['repo'] = 'other/cli'
        value = catalog(); value['resources']['doc']['origin']['upstream']['repo'] = 'other/cli'
        result = update_groups(value, report)
        self.assertEqual(sorted(len(names) for _, names in result), [1, 1])

    def test_shared_dependency_failure_is_not_hidden_by_a_partial_batch(self):
        value = catalog()
        for n in ['apps', 'doc']: value['resources'][n]['source']['dependencies'] = ['shared']
        report = checked(); report['results'][1]['status'] = 'check_failed'
        self.assertEqual(update_groups(value, report), [('shared-apps', ['apps', 'doc'])])

    def test_batch_name_is_stable_when_only_one_resource_changes(self):
        report = checked(); report['results'][1]['status'] = 'no_change'
        self.assertEqual(update_groups(catalog(), report), [(upstream_group('larksuite/cli'), ['apps'])])
        self.assertNotEqual(upstream_group('a-b/c'), upstream_group('a/b-c'))

    def test_batch_members_may_change_but_not_repository_or_declined_target(self):
        old = state(); old['branch'] = 'claudespace/update/fixture/'+upstream_group('owner/upstream')
        new = deepcopy(old); new['updates']['second'] = deepcopy(new['updates']['demo'])
        self.assertTrue(same_scope(old, new))
        remote = {'base_sha': new['base_commit'], 'head_sha': old['generated_head'], 'pr': pr_for(old, state='closed')}
        self.assertEqual(decide(new, remote, 'github-actions[bot]')['action'], 'declined')
        new['updates']['second']['repo'] = 'different/repo'
        self.assertFalse(same_scope(old, new))
