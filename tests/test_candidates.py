import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('candidates', ROOT / 'scripts/build_candidates.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)


class CandidateIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.domain = Path(self.temp.name)
        catalog = json.loads((module.DOMAIN / 'catalog.json').read_text())
        self.item = copy.deepcopy(next(p for p in catalog['plugins'] if p['name'] == 'code-review'))
        shutil.copytree(module.DOMAIN / 'packages/code-review', self.domain / 'packages/code-review')
        self.override = patch.object(module, 'DOMAIN', self.domain); self.override.start()

    def tearDown(self):
        self.override.stop(); self.temp.cleanup()

    def test_upstream_edit_is_detected(self):
        source = self.domain / 'packages/code-review/skills/code-review/SKILL.md'
        source.write_text(source.read_text() + '\nUnauthorized change\n')
        with self.assertRaisesRegex(ValueError, 'Upstream file changed'):
            module.validate({'plugins': [self.item]})

    def test_packaging_revision_drift_is_detected(self):
        self.item['packaging_revision'] += 1
        with self.assertRaisesRegex(ValueError, 'packaging version mismatch'):
            module.validate({'plugins': [self.item]})

    def test_automatic_install_selection_is_rejected(self):
        self.item['default_install'] = True
        with self.assertRaisesRegex(ValueError, 'explicitly selected'):
            module.validate({'plugins': [self.item]})


if __name__ == '__main__':
    unittest.main()
