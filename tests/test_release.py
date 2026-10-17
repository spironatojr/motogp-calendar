import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

from scripts import release


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / 'plugin').mkdir()
        (self.root / 'VERSION').write_text('1.0.0\n')
        (self.root / 'plugin/manifest.json').write_text(json.dumps({'version': '1.0.0'}))
        (self.root / 'CHANGELOG.md').write_text(
            '# Changelog\n\n## [Unreleased]\n\n### Added\n\n- A new feature.\n\n'
            '## [1.0.0] - 2026-10-17\n\n- Initial release.\n')

    def test_mismatched_tag_plugin_and_missing_notes_are_rejected(self):
        self.assertEqual(release.check(self.root, 'v1.0.0'), '1.0.0')
        with self.assertRaises(ValueError):
            release.check(self.root, 'v1.0.1')
        (self.root / 'plugin/manifest.json').write_text('{"version":"1.0.1"}')
        with self.assertRaises(ValueError):
            release.check(self.root)
        (self.root / 'plugin/manifest.json').write_text('{"version":"1.0.0"}')
        (self.root / 'CHANGELOG.md').write_text('# Changelog\n')
        with self.assertRaises(ValueError):
            release.check(self.root)

    def test_prepare_moves_notes_and_keeps_the_previous_release(self):
        release.prepare(self.root, '1.1.0-rc.1')
        self.assertEqual(release.check(self.root, 'v1.1.0-rc.1'), '1.1.0-rc.1')
        self.assertIn('- A new feature.', release.release_notes(self.root, '1.1.0-rc.1'))
        self.assertEqual(release.release_notes(self.root, '1.0.0'), '- Initial release.\n')
        before = (self.root / 'CHANGELOG.md').read_bytes()
        with self.assertRaises(ValueError):
            release.prepare(self.root, '1.1.0')  # Unreleased is now empty.
        self.assertEqual((self.root / 'CHANGELOG.md').read_bytes(), before)

    def test_prepare_rejects_invalid_or_older_versions_without_writing(self):
        for version in ('0.9.0', '1.0.0', '1.0.0-rc.1', '01.0.1', '1.1.0-rc.01', 'v1.1.0'):
            with self.subTest(version=version), self.assertRaises(ValueError):
                release.prepare(self.root, version)
        self.assertEqual(release.check(self.root), '1.0.0')
        self.assertLess(release.version_key('1.1.0-rc.2'), release.version_key('1.1.0-rc.10'))
        self.assertLess(release.version_key('1.1.0-rc.10'), release.version_key('1.1.0'))

    def test_package_is_reproducible_complete_and_runs_without_gtk(self):
        archive = release.build(release.ROOT, self.root / 'first')
        another = release.build(release.ROOT, self.root / 'second')
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        self.assertEqual(archive.read_bytes(), another.read_bytes())
        self.assertEqual((archive.parent / 'SHA256SUMS').read_text(), f'{digest}  {archive.name}\n')
        version = release.check(release.ROOT)
        prefix = f'motogp-calendar-{version}/'
        with tarfile.open(archive) as bundle:
            members = bundle.getnames()
            for required in release.PAYLOAD_FILES:
                self.assertIn(prefix + required, members)
            self.assertEqual(len([n for n in members if n.startswith(prefix + 'circuits/')
                                  and n.endswith('.png')]), 22)
            self.assertIn(prefix + 'icons/calendar-arrow-down.svg', members)
            self.assertEqual(bundle.getmember(prefix + 'plugin/bin/motogp-calendar').mode, 0o755)
            for name in members:
                parts = Path(name).parts
                self.assertFalse(any(p in ('.git', 'backups', '__pycache__', '.env') for p in parts), name)
            bundle.extractall(self.root / 'extracted', filter='data')
        extracted = self.root / 'extracted' / prefix
        result = subprocess.check_output([sys.executable, '-S', 'app.py', '--version'],
                                         cwd=extracted, text=True)
        self.assertEqual(result.strip(), f'MotoGP Calendar {version}')
        status = subprocess.check_output([sys.executable, '-S', 'app.py', '--status'],
                                         cwd=extracted, text=True)
        self.assertIn('label', json.loads(status))


class InstallVersionTests(unittest.TestCase):
    def test_installer_copies_the_version_and_preserves_existing_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            commands = home / 'bin'
            commands.mkdir()
            for name in ('omarchy', 'omarchy-shell', 'hyprctl', 'update-desktop-database'):
                command = commands / name
                command.write_text('#!/bin/sh\nexit 0\n')
                command.chmod(0o755)
            config = home / 'config'
            (config / 'hypr').mkdir(parents=True)
            (config / 'hypr/hyprland.lua').write_text('-- Existing configuration\n')
            data = home / 'data'
            cache = home / 'cache/motogp-calendar'
            cache.mkdir(parents=True)
            saved = cache / '2026.json'
            saved.write_text('keep this user cache')
            # Import the real installer, redirect every destination and its backup
            # into the temporary home, and run it against fake desktop commands.
            driver = '''
import os
from pathlib import Path
import install
install.HOME = Path(os.environ['HOME'])
install.DATA = Path(os.environ['XDG_DATA_HOME'])
install.CONFIG = Path(os.environ['XDG_CONFIG_HOME'])
install.APP = install.DATA / 'motogp-calendar'
install.PLUGIN = install.CONFIG / 'omarchy/plugins/local.motogp'
install.BACKUP = install.HOME / 'backups'
install.main()
'''
            env = dict(os.environ, HOME=str(home), XDG_DATA_HOME=str(data),
                       XDG_CONFIG_HOME=str(config), XDG_CACHE_HOME=str(home / 'cache'),
                       PATH=str(commands) + os.pathsep + os.environ['PATH'])
            subprocess.run([sys.executable, '-c', driver], cwd=release.ROOT, env=env,
                           check=True, capture_output=True, text=True)
            installed = data / 'motogp-calendar'
            version = release.check(release.ROOT)
            result = subprocess.check_output([sys.executable, '-S', str(installed / 'app.py'), '--version'],
                                             env=env, text=True)
            self.assertEqual(result.strip(), f'MotoGP Calendar {version}')
            self.assertEqual(json.loads((config / 'omarchy/plugins/local.motogp/manifest.json').read_text())['version'],
                             version)
            self.assertEqual(saved.read_text(), 'keep this user cache')


if __name__ == '__main__':
    unittest.main()
