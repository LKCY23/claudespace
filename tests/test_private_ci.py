"""Private CI uses temporary Git fixtures; keys and source text never leave tests."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shlex
import sys
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import private_ci as module
import run_updates
import test_prepare_update as fixtures

KEY = '-----BEGIN OPENSSH PRIVATE KEY-----\nTEST-KEY-NEVER-PUBLISH\n-----END OPENSSH PRIVATE KEY-----\n'
RULES = {'owner/upstream': {'key_env': 'CLAUDESPACE_TEST_KEY'}}


class PrivateSourceTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.PrepareTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.f.item['update']['target'] = self.f.git(self.f.upstream, 'branch', '--show-current')
        self.f.save(); self.key_paths = []
        real_git = module.git
        def local_transport(root, *args, **kwargs):
            if 'fetch' in args:
                config = next(arg for arg in args if arg.startswith('core.sshCommand='))
                command = shlex.split(config.split('=', 1)[1]); key = Path(command[command.index('-i') + 1])
                self.key_paths.append(key)
                self.assertEqual(key.read_text(), KEY)
                self.assertEqual(key.stat().st_mode & 0o777, 0o600)
                self.assertNotIn('CLAUDESPACE_TEST_KEY', os.environ)
                self.assertNotIn(KEY, str(args))
                for value in ('/dev/null', '443', 'IdentityAgent=none', 'IdentitiesOnly=yes', 'StrictHostKeyChecking=yes', 'HostKeyAlias=github.com'):
                    self.assertIn(value, command)
                return real_git(root, 'fetch', '--quiet', '--no-tags', str(self.f.upstream), args[-1])
            return real_git(root, *args, **kwargs)
        self.addCleanup(patch.stopall)
        patch.object(module, 'git', side_effect=local_transport).start()
        patch.dict(os.environ, {'CLAUDESPACE_TEST_KEY': KEY}).start()

    def test_fixed_source_access_and_key_cleanup(self):
        with module.private_sources(self.f.source, RULES) as (prepared, targets):
            self.assertEqual(targets, {})
            self.assertEqual(self.f.git(prepared['owner/upstream'], 'rev-parse', self.f.old), self.f.old)
            self.assertTrue(all(p.is_file() for p in self.key_paths))
        self.assertTrue(self.key_paths)
        self.assertTrue(all(not p.exists() for p in self.key_paths))

    def test_cleanup_also_runs_on_validation_failure(self):
        with self.assertRaisesRegex(ValueError, 'synthetic'):
            with module.private_sources(self.f.source, RULES):
                raise ValueError('synthetic')
        self.assertTrue(all(not p.exists() for p in self.key_paths))

    def test_missing_key_fails_with_safe_saved_report(self):
        os.environ.pop('CLAUDESPACE_TEST_KEY')
        report = self.f.root/'report.json'
        result = module.validate_sources(self.f.source, report, RULES)
        self.assertEqual(result['status'], 'failed')
        self.assertNotIn(KEY, report.read_text())
        self.assertFalse(self.key_paths)

    def test_public_import_of_private_bodies_is_rejected(self):
        for kind in ('tracked', 'submodule'):
            with self.subTest(kind=kind):
                source = deepcopy(self.f.item['source']); source['kind'] = kind
                if kind == 'tracked': source = {'kind':'tracked','path':'private-body'}
                with patch.object(module, 'read_catalog', return_value={**self.f.catalog, 'resources':{'demo':{**self.f.item,'source':source}}}):
                    with self.assertRaisesRegex(ValueError, 'remain external'):
                        module.private_items(self.f.source, RULES)

    def test_success_report_keeps_only_counts_and_catalog_status(self):
        result = module.validate_sources(self.f.source, self.f.root/'public.json', RULES)
        self.assertEqual(result['status'], 'passed'); self.assertEqual(result['resource_count'],1)
        text = (self.f.root/'public.json').read_text()
        self.assertNotIn('SKILL.md', text); self.assertNotIn('original', text); self.assertNotIn(KEY,text)
        self.assertFalse(result['private_bodies_published'])
        self.assertTrue(all(not p.exists() for p in self.key_paths))

    def test_raw_exception_and_private_content_are_not_serialized(self):
        with patch.object(module, 'validate', side_effect=ValueError(KEY+' private-body-secret')):
            result = module.validate_sources(self.f.source,self.f.root/'public.json',RULES)
        text=json.dumps(result)
        self.assertEqual(result['status'],'failed');self.assertNotIn(KEY,text);self.assertNotIn('private-body-secret',text)
        self.assertTrue(all(not p.exists() for p in self.key_paths))

    def test_git_tracking_updates_pin_without_publishing_private_paths_or_body(self):
        (self.f.upstream/'private-only-reference.md').write_text('PRIVATE-SOURCE-CONTENT')
        self.f.commit(self.f.upstream); target=self.f.git(self.f.upstream,'rev-parse','HEAD')
        with module.private_sources(self.f.source,RULES,tracking=True) as (prepared,targets):
            public=unittest.mock.Mock(side_effect=AssertionError('Unexpected public query'))
            api=module.SourceAPI(prepared,targets,public)
            output=self.f.root/'batch'
            report=run_updates.run(self.f.source,output,api=api,prepared=prepared,private_repos=RULES)
        self.assertEqual(report['status'],'ok');self.assertEqual(len(report['candidates']),1)
        checked=json.loads((output/'checks/fixture.json').read_text())['results'][0]
        self.assertEqual(checked['target_commit'],target)
        self.assertTrue(checked['private_details_redacted']);self.assertGreater(checked['changed_files_count'],0)
        self.assertNotIn('changed_files',checked)
        for path in output.rglob('*.json'):
            text=path.read_text()
            self.assertNotIn('private-only-reference',text);self.assertNotIn('PRIVATE-SOURCE-CONTENT',text);self.assertNotIn(KEY,text)

    def test_private_release_tracking_is_explicitly_unsupported(self):
        self.f.item['update']={'strategy':'release','target':'latest'};self.f.save()
        with self.assertRaisesRegex(ValueError,'branch or manual'):
            with module.private_sources(self.f.source,RULES,tracking=True):pass
        self.assertTrue(all(not p.exists() for p in self.key_paths))

    def test_private_group_build_errors_do_not_publish_source_paths(self):
        with module.private_sources(self.f.source,RULES,tracking=True) as (prepared,targets):
            api=module.SourceAPI(prepared,targets,unittest.mock.Mock())
            with patch.object(run_updates,'prepare',side_effect=ValueError('Missing private-only-reference.md '+KEY)):
                output=self.f.root/'batch'
                report=run_updates.run(self.f.source,output,api=api,prepared=prepared,private_repos=RULES)
        self.assertEqual(report['status'],'needs_attention')
        text=(output/'index.json').read_text()+run_updates.summary(report)
        self.assertNotIn('private-only-reference.md',text);self.assertNotIn(KEY,text)

    def test_private_access_failure_keeps_public_candidates(self):
        os.environ.pop('CLAUDESPACE_TEST_KEY')
        public_source=self.f.root/'public-upstream'
        self.f.git(self.f.root,'clone','--quiet',str(self.f.upstream),str(public_source))
        self.f.git(public_source,'remote','set-url','origin','https://github.com/owner/public.git')
        item=deepcopy(self.f.item);item['source']['repo']='owner/public';item['origin']['upstream']['repo']='owner/public'
        self.f.catalog['resources']['public']=item;self.f.save()
        public_api=unittest.mock.Mock(side_effect=lambda repo,route: {'sha':self.f.new} if route.startswith('commits/') else {'status':'ahead','files':[{'filename':'SKILL.md'}]})
        with module.private_sources(self.f.source,RULES,tracking=True,tolerate_errors=True) as (prepared,targets):
            self.assertEqual(prepared,{})
            api=module.SourceAPI(prepared,targets,public_api,RULES)
            output=self.f.root/'batch'
            report=run_updates.run(self.f.source,output,api=api,prepared={'owner/public':public_source},private_repos=RULES)
        self.assertEqual(report['status'],'needs_attention');self.assertEqual(len(report['candidates']),1)
        checked=json.loads((output/'checks/fixture.json').read_text())
        self.assertEqual(checked['counts']['check_failed'],1)
        self.assertTrue(all(call.args[0]=='owner/public' for call in public_api.call_args_list))

    def test_private_policy_is_loaded_from_trusted_tool_not_candidate(self):
        candidate_policy=self.f.source/'ci/private-sources.json';candidate_policy.parent.mkdir()
        candidate_policy.write_text('{"schema_version":1,"repositories":{}}')
        self.assertIn('LKCY23/goal-authoring',module.policy())

    def test_public_only_selection_also_removes_unused_keys_from_environment(self):
        with patch.object(module,'private_items',return_value=[]):
            with module.private_sources(self.f.source,RULES) as (prepared,targets):
                self.assertEqual(prepared,{});self.assertEqual(targets,{})
                self.assertNotIn('CLAUDESPACE_TEST_KEY',os.environ)
        self.assertFalse(self.key_paths)

    def test_catalog_symlink_cannot_select_data_outside_the_inspected_commit(self):
        outside=self.f.root/'outside.json';outside.write_bytes(self.f.file.read_bytes())
        self.f.file.unlink();self.f.file.symlink_to(outside)
        with self.assertRaisesRegex(ValueError,'inside the inspected'):
            module.private_items(self.f.source,RULES)

    def test_public_queries_keep_the_existing_api(self):
        public=unittest.mock.Mock(return_value={'sha':'a'*40})
        self.assertEqual(module.SourceAPI({}, {}, public)('public/repo','commits/main'),{'sha':'a'*40})
        public.assert_called_once_with('public/repo','commits/main')

    def test_prepare_setup_failure_has_saved_batch_report(self):
        os.environ.pop('CLAUDESPACE_TEST_KEY')
        output=self.f.root/'batch'
        with patch.object(module,'policy',return_value=RULES):
            code=module.main(['prepare','--root',str(self.f.source),'--output',str(output)])
        self.assertEqual(code,1)
        report=json.loads((output/'index.json').read_text())
        self.assertEqual(report['status'],'needs_attention');self.assertEqual(report['candidates'],[])
        self.assertEqual(report['checks'][0]['counts']['check_failed'],1)


class PrivateWorkflowTests(unittest.TestCase):
    def read(self,name):return yaml.load((ROOT/'.github/workflows'/name).read_text(),Loader=yaml.BaseLoader)

    def test_pr_tests_have_no_secret_or_private_source_execution(self):
        value=self.read('validate-resources.yml')
        self.assertIn('pull_request',value['on'])
        self.assertNotIn('secrets.',str(value));self.assertNotIn('environment',value['jobs']['validate'])
        self.assertNotIn('private_ci.py',str(value));self.assertNotIn('validate_catalogs.py',str(value))

    def test_privileged_validation_executes_trusted_code_and_uploads_only_report(self):
        value=self.read('validate-fixed-sources.yml');job=value['jobs']['validate']
        self.assertNotIn('pull_request_target',value['on']);self.assertNotIn('pull_request',value['on'])
        self.assertEqual(job['environment'],'claudespace-private-sources')
        self.assertIn('CLAUDESPACE_PRIVATE_CI_PREVIEW_REF',job['if'])
        checkouts=[s for s in job['steps'] if s.get('uses','').startswith('actions/checkout@')]
        self.assertEqual(checkouts[0]['with']['ref'],'${{ github.sha }}')
        self.assertEqual([s['with']['path'] for s in checkouts],['validator','candidate'])
        run='\n'.join(s.get('run','') for s in job['steps'])
        self.assertIn('validator/scripts/private_ci.py',run)
        self.assertNotIn('candidate/scripts/',run);self.assertNotIn('unittest',run);self.assertNotIn('pip install',run)
        upload=next(s for s in job['steps'] if s.get('uses','').startswith('actions/upload-artifact@'))
        self.assertEqual(upload['with']['path'],'${{ runner.temp }}/fixed-source-validation.json')
        self.assertIn('statuses/$SOURCE_COMMIT',run)

    def test_only_trusted_preparation_and_baseline_jobs_receive_private_key(self):
        for name,job_name in [('resource-updates.yml','prepare'),('publish-baseline.yml','baseline')]:
            job=self.read(name)['jobs'][job_name]
            self.assertIn('default_branch',job['if']);self.assertEqual(job['environment'],'claudespace-private-sources')
            for step in job['steps']:
                if 'CLAUDESPACE_GOAL_AUTHORING_KEY' in step.get('env',{}):self.assertIn('private_ci.py',step['run'])
        publisher=self.read('resource-updates.yml')['jobs']['pull_requests']
        self.assertNotIn('CLAUDESPACE_GOAL_AUTHORING_KEY',str(publisher))


if __name__=='__main__':unittest.main()
