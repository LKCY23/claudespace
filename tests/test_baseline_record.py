import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from baseline_record import build_record
from test_updates import catalog


class BaselineRecordTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'isolated')
        self.git('config', 'user.email', 'isolated@example.invalid')
        self.git('remote', 'add', 'origin', 'https://github.com/owner/catalog.git')
        (self.root / 'catalog.json').write_text(json.dumps(catalog()))
        self.git('add', '.')
        self.git('commit', '-qm', 'fixture')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], capture_output=True, text=True, check=True).stdout.strip()

    def test_record_has_exact_commit_and_catalog_bytes_without_self_reference(self):
        value = build_record(self.root)
        self.assertEqual(value['commit'], self.git('rev-parse', 'HEAD'))
        self.assertEqual(value['catalog_sha256'], hashlib.sha256((self.root / 'catalog.json').read_bytes()).hexdigest())
        self.assertEqual(value['validation']['level'], 'structural')
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_dirty_catalog_and_wrong_repository_root_block(self):
        (self.root / 'extra').write_text('extra')
        with self.assertRaises(ValueError):
            build_record(self.root)
        with self.assertRaises((ValueError, subprocess.SubprocessError)):
            build_record(self.root.parent)

    def test_failed_compatibility_not_marked_as_published_passing(self):
        value = json.loads((self.root / 'catalog.json').read_text())
        value['resources']['one']['compatibility']['codex']['validation'] = {'status': 'failed', 'level': 'structural', 'evidence': 'failed.json'}
        (self.root / 'catalog.json').write_text(json.dumps(value))
        self.git('add', '.')
        self.git('commit', '-qm', 'failed compatibility')
        with self.assertRaises(ValueError):
            build_record(self.root)

    def test_hidden_local_catalog_change_and_escaping_path_block(self):
        self.git('update-index', '--assume-unchanged', 'catalog.json')
        (self.root / 'catalog.json').write_text(json.dumps(catalog()) + ' ')
        with self.assertRaises(ValueError):
            build_record(self.root)
        with self.assertRaises(ValueError):
            build_record(self.root, '../')


if __name__ == '__main__':
    unittest.main()
