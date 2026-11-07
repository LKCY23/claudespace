"""Trusted PR routing and exact-head reporting; no live GitHub writes."""
from copy import deepcopy
from pathlib import Path
import sys
import subprocess
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import pr_validation as module
from sync_update_prs import GitHubPRs
from unittest.mock import patch


def pr():
    return {'number': 12, 'state': 'open', 'head': {'sha': 'a'*40, 'ref': 'feature', 'repo': {'full_name': 'owner/repo'}},
            'base': {'ref': 'main', 'repo': {'full_name': 'owner/repo'}}}


class Hub:
    repo = 'owner/repo'
    def __init__(self):
        self.pr = pr(); self.posts = []
        self.run = {'event': 'pull_request', 'path': '.github/workflows/validate-resources.yml',
                    'head_sha': 'a'*40, 'head_branch': 'feature', 'head_repository': {'full_name': self.repo}}
    def api(self, method, path, payload=None):
        if method == 'POST': self.posts.append((path, payload)); return {}
        if path == '': return {'default_branch': 'main'}
        if path.startswith('actions/runs/'): return self.run
        if path.startswith('pulls?'): return [self.pr]
        if path.startswith('pulls/'): return self.pr
        raise AssertionError(path)


class RoutingTests(unittest.TestCase):
    def test_repository_metadata_api_has_no_trailing_slash(self):
        with patch('sync_update_prs.subprocess.run', return_value=subprocess.CompletedProcess([],0,'{"default_branch":"main"}','')) as run:
            self.assertEqual(GitHubPRs('owner/repo').api('GET','')['default_branch'],'main')
            self.assertEqual(run.call_args.args[0][-1],'repos/owner/repo')

    def test_dispatch_selects_exact_open_same_repo_head(self):
        hub = Hub()
        self.assertEqual(module.select(hub, {}, number='12', expected='a'*40), hub.pr)
        self.assertIsNone(module.select(hub, {}, number='12', expected='b'*40))
        for edit in [lambda p:p.update(state='closed'), lambda p:p['head'].update(repo=None),
                     lambda p:p['head']['repo'].update(full_name='fork/repo'), lambda p:p['base'].update(ref='other')]:
            hub.pr = pr(); edit(hub.pr)
            self.assertIsNone(module.select(hub, {}, number='12', expected='a'*40))

    def test_invalid_inputs_and_unrelated_or_fork_runs_do_not_dispatch(self):
        hub = Hub()
        with self.assertRaises(ValueError): module.select(hub, {}, number='12;echo bad', expected='a'*40)
        with self.assertRaises(ValueError): module.select(hub, {}, number='12', expected='main')
        event = {'workflow_run': {'id': 5}}
        self.assertEqual(module.select(hub, event), hub.pr)
        for key, value in [('event', 'push'), ('path', '.github/workflows/other.yml'), ('head_repository', {'full_name':'fork/repo'})]:
            old = deepcopy(hub.run); hub.run[key] = value
            self.assertIsNone(module.select(hub, event)); hub.run = old

    def test_report_cannot_credit_a_new_head_or_turn_skips_into_success(self):
        hub = Hub()
        self.assertEqual(module.finish(hub,12,'a'*40,'success','success','https://example.invalid/run'), 'ready-for-review')
        self.assertEqual(hub.posts[0][1]['state'], 'success')
        hub.posts.clear(); hub.pr['head']['sha'] = 'b'*40
        self.assertEqual(module.finish(hub,12,'a'*40,'success','success','url'), 'superseded'); self.assertEqual(hub.posts, [])
        hub.pr = pr()
        self.assertEqual(module.finish(hub,12,'a'*40,'cancelled','skipped','url'), 'needs-attention')
        self.assertEqual([p['state'] for _, p in hub.posts], ['failure', 'failure'])

    def test_successful_statuses_deduplicate_dispatch_but_failure_retries(self):
        hub = GitHubPRs('owner/repo')
        statuses = [{'context':c,'state':'success'} for c in ['Tooling tests','claudespace/fixed-sources']]
        with patch.object(hub,'api',return_value={'statuses':statuses}) as api:
            self.assertFalse(hub.request_validation(12,'a'*40,'main')); self.assertEqual(api.call_count,1)
        with patch.object(hub,'api',side_effect=[{'statuses':[]},None]) as api:
            self.assertTrue(hub.request_validation(12,'a'*40,'main'))
            self.assertEqual(api.call_args.args[2], {'ref':'main','inputs':{'pr':'12','head':'a'*40}})


class WorkflowTests(unittest.TestCase):
    def test_untrusted_tests_and_privileged_reports_are_separate_jobs(self):
        value = yaml.load((ROOT/'.github/workflows/pr-validation.yml').read_text(), Loader=yaml.BaseLoader)
        self.assertNotIn('pull_request_target', value['on'])
        self.assertEqual(value['on']['workflow_run']['workflows'], ['Validate tooling'])
        jobs = value['jobs']; tooling = jobs['tooling']
        self.assertEqual(tooling['permissions'], {'contents':'read'})
        self.assertNotIn('environment',tooling); self.assertNotIn('secrets.',str(tooling)); self.assertNotIn('GH_TOKEN',str(tooling))
        self.assertEqual(tooling['steps'][0]['with']['ref'],'${{ needs.select.outputs.head }}')
        for name in ('select','report'):
            self.assertEqual(jobs[name]['steps'][0]['with']['ref'],'${{ github.sha }}')
            self.assertNotIn('needs.select.outputs.head',str(jobs[name]['steps'][0]))
        self.assertEqual(jobs['fixed_sources']['uses'],'./.github/workflows/validate-fixed-sources.yml')
        self.assertEqual(jobs['fixed_sources']['with']['commit'],'${{ needs.select.outputs.head }}')
        keys = ('CLAUDESPACE_GOAL_AUTHORING_KEY', 'CLAUDESPACE_CLAUDE_SANCTUARY_KEY')
        self.assertEqual(jobs['fixed_sources']['secrets'], {key: '${{ secrets.' + key + ' }}' for key in keys})
        for name in ('select', 'tooling', 'report'):
            self.assertNotIn('CLAUDESPACE_GOAL_AUTHORING_KEY', str(jobs[name]))
            self.assertNotIn('CLAUDESPACE_CLAUDE_SANCTUARY_KEY', str(jobs[name]))
        fixed = yaml.load((ROOT/'.github/workflows/validate-fixed-sources.yml').read_text(),Loader=yaml.BaseLoader)
        self.assertIn('workflow_call',fixed['on'])
        self.assertEqual(fixed['on']['workflow_call']['secrets'], {key: {'required': 'true'} for key in keys})


if __name__ == '__main__': unittest.main()
