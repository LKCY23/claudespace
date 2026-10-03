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
        self.simplifier = copy.deepcopy(next(p for p in catalog['plugins'] if p['name'] == 'code-simplifier'))
        shutil.copytree(module.DOMAIN / 'packages/code-simplifier', self.domain / 'packages/code-simplifier')
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

    def test_missing_original_rule_is_rejected_without_writing_package(self):
        rule = self.domain / 'packages/code-simplifier/agents/code-simplifier.md'
        rule.unlink()
        before = {str(p.relative_to(self.domain)): p.read_bytes()
                  for p in self.domain.rglob('*') if p.is_file()}
        with self.assertRaisesRegex(ValueError, 'Missing or escaping package reference'):
            module.validate({'plugins': [self.simplifier]})
        after = {str(p.relative_to(self.domain)): p.read_bytes()
                 for p in self.domain.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_missing_manifest_component_is_rejected(self):
        manifest = self.domain / 'packages/code-review/.codex-plugin/plugin.json'
        value = json.loads(manifest.read_text()); value['skills'] = './missing-skills/'
        manifest.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'Missing or escaping package reference'):
            module.validate({'plugins': [self.item]})

    def test_existing_directory_that_hides_entry_is_rejected(self):
        manifest = self.domain / 'packages/code-simplifier/.codex-plugin/plugin.json'
        value = json.loads(manifest.read_text()); value['skills'] = './agents/'
        manifest.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'must expose one'):
            module.validate({'plugins': [self.simplifier]})

    def test_rule_reference_is_checked_independently_of_template_equality(self):
        package = self.domain / 'packages/code-simplifier'
        entry = package / 'codex/skills/code-simplifier/SKILL.md'
        entry.write_text(entry.read_text().replace('../../../agents/code-simplifier.md', '../../../../agents/code-simplifier.md'))
        with self.assertRaisesRegex(ValueError, 'Missing or escaping package reference'):
            module.validate({'plugins': [self.simplifier]})

    def test_relocated_installed_layout_resolves_same_original_bytes(self):
        installed = self.domain / 'cache/candidates/code-simplifier/packaging-version'
        shutil.copytree(self.domain / 'packages/code-simplifier', installed)
        manifest = json.loads((installed / '.codex-plugin/plugin.json').read_text())
        module.validate_simplifier_entry(installed, manifest)
        self.assertEqual((installed / 'agents/code-simplifier.md').read_bytes(),
                         (self.domain / 'packages/code-simplifier/agents/code-simplifier.md').read_bytes())

    def test_exported_entry_cannot_link_outside_package(self):
        package = self.domain / 'packages/code-simplifier'
        entry = package / 'codex/skills/code-simplifier/SKILL.md'
        external = self.domain / 'outside-skill.md'; external.write_bytes(entry.read_bytes())
        entry.unlink(); entry.symlink_to(external)
        with self.assertRaisesRegex(ValueError, 'entry escapes its package'):
            module.validate({'plugins': [self.simplifier]})


if __name__ == '__main__':
    unittest.main()
