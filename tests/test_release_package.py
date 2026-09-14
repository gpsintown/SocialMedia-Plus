import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

PACKAGE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release_check', PACKAGE / 'scripts/release-check.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def test_export_excludes_populated_runtime_and_keeps_skill_roles(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            root = parent / 'workspace'
            root.mkdir()
            files = {name: 'Public fixture' for name in release.REQUIRED_FILES}
            files.update({
                'README.md': 'Public source', '.env.example': 'LINKEDIN_PUBLISH_CLIENT_SECRET=\n',
                '.env.local': 'fixture private credential', 'profile/resume.pdf': 'private resume',
                'data/socialmediaplus.sqlite3': 'private database',
                'config/settings.json': '{"owner":"private member"}',
                'runtime/install/codex-mcp.toml': 'private binding',
                '.agents/council/reader.md': 'Readability reviewer',
                '.claude/agents/reader.md': 'Readability reviewer',
                '.git/config': 'private remote', 'ui/node_modules/pkg/index.js': 'dependency',
            })
            for name, value in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(value)
            output = parent / 'public.zip'
            result = subprocess.run([sys.executable, str(PACKAGE / 'scripts/build-release.py'),
                                     '--root', str(root), '--output', str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                self.assertIn('social-media-plus/.agents/council/reader.md', names)
                self.assertIn('social-media-plus/.env.example', names)
                self.assertFalse(any('private' in archive.read(name).decode() for name in names))
                self.assertEqual(len(names), len(release.candidates(root)) + 1)
                manifest = json.loads(archive.read('social-media-plus/RELEASE-MANIFEST.json'))
                for name, expected in manifest['files'].items():
                    self.assertEqual(release.hashlib.sha256(archive.read('social-media-plus/' + name)).hexdigest(), expected)

    def test_audit_blocks_embedded_secret_and_symlink_without_echo(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'docs').mkdir()
            secret = 'ghp_' + 'A' * 36
            (root / 'docs/leak.md').write_text(secret)
            result = release.audit(root, require_complete=False)
            self.assertFalse(result['ok'])
            self.assertNotIn(secret, json.dumps(result))
            (root / 'docs/leak.md').unlink()
            (root / 'docs/link.md').symlink_to(root / 'missing-secret')
            self.assertFalse(release.audit(root, require_complete=False)['ok'])

    def test_template_profiles_are_empty_and_permissions_are_not_inherited(self):
        settings = json.loads((PACKAGE / 'templates/config/settings.json').read_text())
        self.assertEqual(settings['owner'], '')
        self.assertEqual(settings['profile_url'], '')
        self.assertEqual(settings['authorizations']['standing'], [])

    def test_missing_required_license_or_runtime_fails_completeness(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = release.audit(Path(temporary))
            self.assertFalse(result['ok'])
            self.assertIn('licenses/react-LICENSE', {x['file'] for x in result['issues']})


if __name__ == '__main__':
    unittest.main()
