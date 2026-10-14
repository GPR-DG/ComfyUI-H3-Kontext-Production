"""Real Git tracking and executable first-install documentation contracts."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PublicationTests(unittest.TestCase):
    def command(self, args, cwd):
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                                encoding='utf-8', errors='replace')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_git_add_does_not_track_credential_or_runtime_files(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder)
            shutil.copyfile(ROOT / '.gitignore', repo / '.gitignore')
            private = ['.env', '.env.production', 'private.env',
                       'config/providers.json', 'config/secrets.private.json',
                       'config/.settings.lock', 'config/runtime.private/result.png',
                       'other/runtime.private/result.png', 'requests.sqlite3',
                       'requests.sqlite3-wal', 'requests.sqlite3-shm',
                       'requests.sqlite3-journal']
            for name in private:
                path = repo / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('SYNTHETIC-PUBLICATION-FIXTURE', encoding='utf-8')
            (repo / 'README.md').write_text('public', encoding='utf-8')
            self.command(['git', 'init'], repo)
            self.command(['git', '-c', 'core.autocrlf=false', 'add', '.'], repo)
            tracked = self.command(['git', 'ls-files'], repo).splitlines()
            self.assertEqual(set(tracked), {'.gitignore', 'README.md'},
                             'Credential/runtime fixture entered actual Git index')

    @unittest.skipUnless(os.name == 'nt', 'Executable first-install PowerShell contract')
    def test_documented_source_initialization_creates_only_missing_config(self):
        readme = (ROOT / 'README.md').read_text(encoding='utf-8-sig')
        blocks = re.findall(r'```powershell\s*\n(.*?)```', readme, re.S)
        initialization = [b for b in blocks if 'Copy-Item' in b and 'providers.example.json' in b]
        self.assertEqual(len(initialization), 1,
                         'README needs executable Git/source-ZIP first-install config copy')
        powershell = shutil.which('powershell') or shutil.which('pwsh')
        self.assertIsNotNone(powershell, 'PowerShell runtime required for this Windows test')
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder) / 'repo'
            repo.mkdir()
            (repo / 'config').mkdir()
            shutil.copyfile(ROOT / '.gitignore', repo / '.gitignore')
            shutil.copyfile(ROOT / 'config/providers.example.json', repo / 'config/providers.example.json')
            self.command(['git', 'init'], repo)
            self.command(['git', '-c', 'core.autocrlf=false', 'add', '.'], repo)
            self.command(['git', '-c', 'user.name=Publication fixture',
                          '-c', 'user.email=fixture@example.invalid', '-c', 'commit.gpgsign=false',
                          'commit', '-m', 'local fixture'], repo)
            clone = Path(folder) / 'clone'
            self.command(['git', 'clone', '--no-hardlinks', str(repo), str(clone)], repo)
            active = clone / 'config/providers.json'
            self.assertFalse(active.exists(), 'Git clone must not receive active user configuration')
            run = [powershell, '-NoProfile', '-NonInteractive', '-Command',
                   "$ErrorActionPreference='Stop'; " + initialization[0]]
            self.command(run, clone)
            self.assertEqual(active.read_bytes(), (ROOT / 'config/providers.example.json').read_bytes())
            self.assertTrue(all(p['enabled'] is False for p in json.loads(active.read_text())['providers']))
            original = b'{"SYNTHETIC_USER_CONFIGURATION":"preserve me"}'
            active.write_bytes(original)
            self.command(run, clone)
            self.assertEqual(active.read_bytes(), original, 'First-install command must not overwrite user settings')


if __name__ == '__main__':
    unittest.main()
