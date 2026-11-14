import base64
from copy import deepcopy
import json
from unittest.mock import patch
import unittest
import auto_merge


class Hub:
    def __init__(self):
        self.files=[{'filename':'.claude-plugin/marketplace.json','status':'modified'}]
        self.data={('a'*40,'marketplaces.json'):json.dumps({'marketplaces':[{'output':'.claude-plugin/marketplace.json'}]}).encode(),
                   ('b'*40,'.claude-plugin/marketplace.json'):b'generated'}
    def api(self,method,path):
        if '/files?' in path:return self.files
        name,sha=path.removeprefix('contents/').split('?ref=')
        return {'type':'file','encoding':'base64','content':base64.b64encode(self.data[sha,name]).decode()}


class AutoMergeTests(unittest.TestCase):
    def setUp(self):
        self.pr={'number':1,'draft':False,'user':{'login':'github-actions[bot]'},'changed_files':1,
                 'base':{'sha':'a'*40},'head':{'sha':'b'*40}}
    def test_only_exact_base_generated_bytes_are_allowed(self):
        h=Hub()
        with patch.object(auto_merge,'render',return_value={'.claude-plugin/marketplace.json':b'generated'}):
            self.assertTrue(auto_merge.marketplace_only(h,self.pr))
            h.data['b'*40,'.claude-plugin/marketplace.json']=b'changed source'
            self.assertFalse(auto_merge.marketplace_only(h,self.pr))
    def test_catalog_code_workflow_and_rename_are_never_automatic(self):
        for path in ['catalog.json','scripts/validate.py','.github/workflows/ci.yml','skills/demo/SKILL.md']:
            h=Hub();h.files[0]['filename']=path
            self.assertFalse(auto_merge.marketplace_only(h,self.pr))
        h=Hub();h.files[0]['previous_filename']='catalog.json'
        self.assertFalse(auto_merge.marketplace_only(h,self.pr))
    def test_human_draft_and_incomplete_diff_are_not_automatic(self):
        for change in [{'draft':True},{'user':{'login':'human'}},{'changed_files':2}]:
            self.assertFalse(auto_merge.marketplace_only(Hub(),dict(self.pr,**change)))
