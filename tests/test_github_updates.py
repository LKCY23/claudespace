"""Remote policy uses a fake API; Git bundles and lease races use temporary repos."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_updates
import sync_update_prs as sync
import test_prepare_update as fixtures


def state():
    return {'schema_version': 1, 'repo': 'owner/catalog', 'base': 'main', 'branch': 'claudespace/update/fixture/demo',
            'catalog': 'fixture', 'catalog_path': 'catalog.json', 'base_commit': 'a'*40, 'generated_head': 'b'*40, 'tree': 'c'*40,
            'updates': {'demo': {'repo': 'owner/upstream', 'from_commit': 'd'*40, 'to_commit': 'e'*40}}}


def pr_for(value, **changes):
    pr = {'number': 7, 'state': 'open', 'merged_at': None, 'title': sync.title(value), 'body': sync.body(value),
          'user': {'login': 'github-actions[bot]'}, 'head': {'repo': {'full_name': value['repo']}, 'ref': value['branch'], 'sha': value['generated_head']},
          'base': {'ref': value['base']}, 'html_url': 'https://github.com/owner/catalog/pull/7'}
    pr.update(changes); return pr


class FakeHub:
    def __init__(self, value, pr=None, head=None):
        self.remote = {'base_sha': value['base_commit'], 'head_sha': head, 'pr': pr}
        self.calls = []; self.fail_pr = False; self.fail_push = False; self.race = False
        self.on_inspect = None
    def inspect(self, branch, base):
        self.calls.append('inspect')
        if self.race and self.calls.count('inspect') == 2: self.remote['head_sha'] = 'f'*40
        if self.on_inspect: self.on_inspect(self.calls.count('inspect'), self.remote)
        return deepcopy(self.remote)
    def push(self, objects, commit, branch, expected):
        self.calls.append('push')
        if self.fail_push: raise ValueError('synthetic push transport failure')
        if self.remote['head_sha'] != expected: raise ValueError('lease rejected')
        self.remote['head_sha'] = commit
    def create(self, value):
        self.calls.append('create')
        if self.fail_pr: raise ValueError('synthetic PR failure')
        self.remote['pr'] = pr_for(value); return self.remote['pr']
    def update(self, number, value):
        self.calls.append('update')
        if self.fail_pr: raise ValueError('synthetic PR failure')
        self.remote['pr'] = pr_for(value); return self.remote['pr']


class PRPolicyTests(unittest.TestCase):
    def test_preview_does_not_write(self):
        value = state(); hub = FakeHub(value)
        result = sync.sync_one(value, Path('/unused'), hub)
        self.assertEqual(result['status'], 'preview'); self.assertEqual(result['action'], 'create')
        self.assertEqual(hub.calls, ['inspect'])

    def test_create_then_identical_tree_reuses_same_pr(self):
        value = state(); hub = FakeHub(value)
        self.assertEqual(sync.sync_one(value, Path('/unused'), hub, write=True)['status'], 'synced')
        self.assertEqual(hub.calls.count('create'), 1)
        again = deepcopy(value); again['generated_head'] = 'f'*40
        self.assertEqual(sync.sync_one(again, Path('/unused'), hub, write=True)['status'], 'unchanged')
        self.assertEqual(hub.calls.count('push'), 1)

    def test_new_target_updates_same_pr_with_expected_head(self):
        old = state(); value = deepcopy(old); value['generated_head'] = 'f'*40; value['tree'] = '1'*40; value['updates']['demo']['to_commit'] = '2'*40
        hub = FakeHub(value, pr_for(old), old['generated_head'])
        result = sync.sync_one(value, Path('/unused'), hub, write=True)
        self.assertEqual(result['status'], 'synced'); self.assertEqual(result['pr_number'], 7)
        self.assertIn('update', hub.calls); self.assertNotIn('create', hub.calls)

    def test_manual_commit_pr_text_author_and_group_changes_block(self):
        value = state()
        edits = [({'head_sha': 'f'*40}, {}), ({}, {'body': sync.body(value)+'\nmanual'}),
                 ({}, {'title': 'manual title'}), ({}, {'user': {'login': 'human'}})]
        for remote, changes in edits:
            with self.subTest(changes=changes, remote=remote):
                hub = FakeHub(value, pr_for(value, **changes), value['generated_head']); hub.remote.update(remote)
                self.assertEqual(sync.sync_one(value, Path('/unused'), hub, write=True)['status'], 'blocked')
                self.assertNotIn('push', hub.calls)
        other = deepcopy(value); other['updates']['extra'] = deepcopy(other['updates']['demo'])
        hub = FakeHub(value, pr_for(other), value['generated_head'])
        self.assertEqual(sync.sync_one(value, Path('/unused'), hub, write=True)['status'], 'blocked')

    def test_closed_rejected_candidate_is_not_recreated(self):
        value = state(); hub = FakeHub(value, pr_for(value, state='closed'), value['generated_head'])
        self.assertEqual(sync.sync_one(value, Path('/unused'), hub, write=True)['status'], 'declined')
        self.assertNotIn('create', hub.calls)

    def test_orphan_branch_only_recovers_the_same_prepared_commit(self):
        value = state(); hub = FakeHub(value, head=value['generated_head'])
        self.assertEqual(sync.sync_one(value, Path('/unused'), hub, write=True)['status'], 'synced')
        self.assertNotIn('push', hub.calls)
        hub = FakeHub(value, head='f'*40)
        self.assertEqual(sync.sync_one(value, Path('/unused'), hub, write=True)['status'], 'blocked')

    def test_default_branch_or_remote_race_stops_before_write(self):
        value = state(); hub = FakeHub(value); hub.remote['base_sha'] = 'f'*40
        self.assertEqual(sync.sync_one(value, Path('/unused'), hub, write=True)['status'], 'blocked')
        hub = FakeHub(value); hub.race = True
        self.assertEqual(sync.sync_one(value, Path('/unused'), hub, write=True)['status'], 'blocked')
        self.assertNotIn('push', hub.calls)

    def test_push_or_pr_failure_reports_uncertainty_and_preserves_branch(self):
        value = state(); hub = FakeHub(value); hub.fail_push = True
        result = sync.sync_one(value, Path('/unused'), hub, write=True)
        self.assertEqual(result['status'], 'partial'); self.assertIsNone(result['remote_branch_updated'])
        hub = FakeHub(value); hub.fail_pr = True
        result = sync.sync_one(value, Path('/unused'), hub, write=True)
        self.assertEqual(result['status'], 'partial'); self.assertTrue(result['remote_branch_updated']); self.assertIsNone(result['pr_updated'])
        hub.fail_pr = False
        self.assertEqual(sync.sync_one(value, Path('/unused'), hub, write=True)['status'], 'synced')
        self.assertEqual(hub.calls.count('push'), 1)

    def test_post_push_base_and_pr_identity_changes_preserve_manual_edits(self):
        old = state(); value = deepcopy(old); value['generated_head'] = 'f'*40; value['tree'] = '1'*40
        edits = [lambda remote: remote.update(base_sha='2'*40),
                 lambda remote: remote['pr']['base'].update(ref='human-target'),
                 lambda remote: remote['pr']['head'].update(ref='human-branch'),
                 lambda remote: remote['pr']['head']['repo'].update(full_name='human/fork'),
                 lambda remote: remote['pr']['user'].update(login='human')]
        for edit in edits:
            with self.subTest(edit=edit):
                hub = FakeHub(value, pr_for(old), old['generated_head'])
                hub.on_inspect = lambda count, remote: edit(remote) if count == 3 else None
                result = sync.sync_one(value, Path('/unused'), hub, write=True)
                self.assertEqual(result['status'], 'partial'); self.assertTrue(result['remote_branch_updated'])
                self.assertFalse(result['pr_updated']); self.assertNotIn('update', hub.calls)

    def test_unmanaged_pr_metadata_does_not_block_refresh(self):
        old = state(); value = deepcopy(old); value['generated_head'] = 'f'*40; value['tree'] = '1'*40
        hub = FakeHub(value, pr_for(old), old['generated_head'])
        hub.on_inspect = lambda count, remote: remote['pr'].update(updated_at=str(count), labels=['human-label'])
        self.assertEqual(sync.sync_one(value, Path('/unused'), hub, write=True)['status'], 'synced')


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PrepareTests(); self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.fixture.save()
    def checked_api(self, repo, route):
        return {'sha': self.fixture.new} if route.startswith('commits/') else {'status':'ahead','files':[{'filename':'SKILL.md'}]}
    def export(self):
        f = self.fixture; output = f.root/'batch'
        report = run_updates.run(f.source, output, api=self.checked_api, prepared={'owner/upstream':f.upstream})
        return output, report
    def test_batch_bundle_is_portable_and_publisher_reads_without_checkout(self):
        f = self.fixture; output, report = self.export(); self.assertEqual(len(report['candidates']),1)
        entry = report['candidates'][0]; receipt = json.loads((output/entry['receipt']).read_text())
        state_value = sync.inspect_bundle(f.source,output/entry['bundle'],receipt,f.root/'objects.git','owner/catalog','main')
        self.assertEqual(state_value['generated_head'],receipt['candidate_commit'])
        self.assertFalse((f.root/'objects.git/catalog.json').exists())
        hub = FakeHub(state_value)
        result = sync.sync_batch(f.source,output,'owner/catalog','main',hub=hub)
        self.assertEqual(result['status'],'ok'); self.assertEqual(hub.calls,['inspect'])
    def test_manual_adaptation_does_not_export_a_candidate(self):
        f = self.fixture; f.item['source']={'kind':'tracked','path':'demo'}; f.item['maintenance']['mode']='adapter'; f.save()
        output,report=self.export()
        self.assertEqual(report['status'],'needs_attention'); self.assertEqual(report['candidates'],[])
    def test_git_timeout_keeps_the_failed_group_and_other_candidates_in_report(self):
        f = self.fixture; f.catalog['resources']['second'] = deepcopy(f.item); f.save()
        original = run_updates.prepare
        def prepare(*args, **kwargs):
            if args[4] == ['demo']: raise subprocess.TimeoutExpired('git fetch', 45)
            return original(*args, **kwargs)
        with patch.object(run_updates, 'prepare', side_effect=prepare): output, report = self.export()
        self.assertEqual(report['status'], 'needs_attention')
        self.assertEqual([row['status'] for row in report['groups']], ['blocked', 'prepared'])
        self.assertEqual(len(report['candidates']), 1)
        self.assertEqual(json.loads((output/'index.json').read_text()), report)
    def test_tampered_receipt_or_extra_code_change_is_rejected(self):
        f=self.fixture;output,report=self.export();entry=report['candidates'][0]
        receipt=json.loads((output/entry['receipt']).read_text());receipt['candidate_commit']='f'*40
        with self.assertRaises(ValueError):sync.inspect_bundle(f.source,output/entry['bundle'],receipt,f.root/'objects.git','owner/catalog','main')
        original=f.prepare();(f.output/'unrelated.py').write_text('do not publish')
        f.git(f.output,'add','.');f.git(f.output,'commit','--amend','--no-edit')
        bad=f.root/'bad.bundle';f.git(f.output,'bundle','create',str(bad),'^'+f.base,original['request']['branch'])
        original['candidate_commit']=f.git(f.output,'rev-parse','HEAD')
        with self.assertRaisesRegex(ValueError,'outside its resource scope'):
            sync.inspect_bundle(f.source,bad,original,f.root/'other-objects.git','owner/catalog','main')
    def test_unselected_discovery_entries_cannot_be_changed(self):
        f = self.fixture
        paths = ['.claude-plugin/marketplace.json', '.agents/plugins/marketplace.json']
        manifest = {'name':'fixture', 'plugins':[
            {'name':'demo', 'source':{'source':'git-subdir','url':'https://github.com/owner/upstream.git','sha':f.old,'path':'.'}},
            {'name':'unrelated', 'source':'./keep'}]}
        for path in paths:
            file = f.source/path; file.parent.mkdir(parents=True); file.write_text(json.dumps(manifest))
        f.save(); receipt = f.prepare()
        for index, path in enumerate(paths):
            with self.subTest(path=path):
                file = f.output/path; incoming = json.loads(file.read_text()); incoming['plugins'][1]['source'] = './unreviewed'
                file.write_text(json.dumps(incoming)); f.git(f.output,'add',path); f.git(f.output,'commit','--amend','--no-edit')
                receipt['candidate_commit'] = f.git(f.output,'rev-parse','HEAD')
                bundle = f.root/('bad-discovery-'+str(index)+'.bundle')
                f.git(f.output,'bundle','create',str(bundle),'^'+f.base,receipt['request']['branch'])
                with self.assertRaisesRegex(ValueError,'unselected discovery'):
                    sync.inspect_bundle(f.source,bundle,receipt,f.root/('objects-'+str(index)), 'owner/catalog','main')
                incoming['plugins'][1]['source'] = './keep'; file.write_text(json.dumps(incoming)); f.git(f.output,'add',path)
    def test_submodule_gitlink_must_match_the_new_pin(self):
        f = self.fixture
        f.item['source'] = {'kind':'submodule','repo':'owner/upstream','commit':f.old,'path':'modules/demo'}
        (f.source/'.gitmodules').write_text('[submodule "demo"]\n path = modules/demo\n url = https://github.com/owner/upstream.git\n')
        f.git(f.source,'update-index','--add','--cacheinfo','160000,'+f.old+',modules/demo')
        (f.source/'modules/demo').mkdir(parents=True)
        f.save(); receipt = f.prepare()
        good = f.root/'good.bundle'; f.git(f.output,'bundle','create',str(good),'^'+f.base,receipt['request']['branch'])
        sync.inspect_bundle(f.source,good,receipt,f.root/'good-objects','owner/catalog','main')
        f.git(f.output,'update-index','--cacheinfo','160000,'+f.old+',modules/demo'); f.git(f.output,'commit','--amend','--no-edit')
        receipt['candidate_commit'] = f.git(f.output,'rev-parse','HEAD')
        bad = f.root/'bad-link.bundle'; f.git(f.output,'bundle','create',str(bad),'^'+f.base,receipt['request']['branch'])
        with self.assertRaisesRegex(ValueError,'gitlink differs'):
            sync.inspect_bundle(f.source,bad,receipt,f.root/'bad-objects','owner/catalog','main')
    def test_real_git_lease_rejects_manual_push(self):
        f=self.fixture;receipt=f.prepare();remote=f.root/'remote.git'
        subprocess.run(['git','clone','--bare',str(f.source),str(remote)],check=True,capture_output=True)
        branch=receipt['request']['branch'];head=receipt['candidate_commit'];ref='refs/heads/'+branch
        real_git = sync.git
        def local_push(root, *args, **kwargs):
            return real_git(root, *[str(remote) if arg == 'https://github.com/owner/catalog.git' else arg for arg in args], **kwargs)
        with patch.object(sync, 'git', side_effect=local_push):
            sync.GitHubPRs('owner/catalog').push(f.output, head, branch, None)
        (f.output/'manual').write_text('human');f.commit(f.output);human=f.git(f.output,'rev-parse','HEAD')
        f.git(f.output,'push',str(remote),human+':'+ref)
        with patch.object(sync, 'git', side_effect=local_push), self.assertRaises(ValueError):
            sync.GitHubPRs('owner/catalog').push(f.output, head, branch, head)
        self.assertEqual(f.git(remote,'rev-parse',ref),human)


class WorkflowTests(unittest.TestCase):
    def read(self,name):return yaml.load((ROOT/'.github/workflows'/name).read_text(),Loader=yaml.BaseLoader)
    def test_read_and_write_jobs_are_separate_and_untrusted_checkout_disabled(self):
        value=self.read('resource-updates.yml');jobs=value['jobs']
        self.assertEqual(value['permissions'],{'contents':'read'})
        self.assertEqual(jobs['pull_requests']['permissions'],{'contents':'write','pull-requests':'write'})
        self.assertIn('needs.prepare.outputs.ready',jobs['pull_requests']['if'])
        for job in jobs.values():
            for step in job['steps']:
                if step.get('uses','').startswith('actions/checkout@'):
                    self.assertEqual(step['with']['persist-credentials'],'false')
        steps=jobs['pull_requests']['steps'];commands='\n'.join(step.get('run','') for step in steps)
        self.assertIn('sync_update_prs.py',commands);self.assertNotIn('unittest',commands)
        self.assertNotIn('pull_request_target',value['on'])
    def test_actions_are_pinned_and_manual_run_previews_by_default(self):
        for path in (ROOT/'.github/workflows').glob('*.yml'):
            value=self.read(path.name)
            for job in value['jobs'].values():
                for step in job['steps']:
                    if 'uses' in step:self.assertRegex(step['uses'],r'^actions/[\w-]+@[0-9a-f]{40}$')
        value=self.read('resource-updates.yml')
        self.assertEqual(value['on']['workflow_dispatch']['inputs']['publish']['default'],'false')
        self.assertEqual(value['on']['schedule'][0]['cron'],'17 1 * * 1')
    def test_baseline_only_follows_final_validation_and_has_no_write_token(self):
        value=self.read('publish-baseline.yml');self.assertEqual(value['permissions'],{'contents':'read'})
        steps=value['jobs']['baseline']['steps'];texts=[step.get('run','') for step in steps]
        self.assertLess(next(i for i,t in enumerate(texts) if 'private_ci.py validate' in t),next(i for i,t in enumerate(texts) if 'build_record' in t))
        self.assertNotIn('pull_request',value['on'])


if __name__=='__main__':unittest.main()
