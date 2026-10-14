"""Packaging must include only declared distributable files."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT.parent / 'work' / 'tmp'

class ReleaseBoundaryTests(unittest.TestCase):
    def test_unknown_files_are_never_written_to_release_zip(self):
        spec = importlib.util.spec_from_file_location('round5_build_release', ROOT / 'scripts/build_release.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(dir=WORK) as folder:
            source = Path(folder) / 'source'; source.mkdir(); (source / 'config').mkdir()
            for name in ('pyproject.toml', 'config/providers.example.json'):
                shutil.copyfile(ROOT / name, source / name)
            names = ['config/secrets.private.json.bak', 'config/providers.backup.json', 'config/key-store.json',
                     'debug.log', 'tokens.txt', 'session.db', 'web/key-copy.js', 'h3_adapter/key_copy.py',
                     'docs/private-notes.md', 'scripts/debug_key.py', 'tests/test_secrets_copy.py']
            for name in names:
                path = source / name; path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('ROUND5-SYNTHETIC-PRIVATE-NOT-A-REAL-KEY', encoding='utf8')
            output = Path(folder) / 'release'
            try:
                result = module.build(source, output)
                archive_path = Path(result['path'])
            except AssertionError:
                archive_path = next(output.glob('*.zip'))
            with zipfile.ZipFile(archive_path) as archive:
                leaked = [n for n in names if 'ComfyUI-H3-Adapter/' + n in archive.namelist()]
                self.assertEqual(leaked, [], 'Private files already written even if builder later raises')
                self.assertEqual(archive.read('ComfyUI-H3-Adapter/config/providers.json'),
                                 (source / 'config/providers.example.json').read_bytes())


    def test_enabled_example_is_rejected_before_archive_write(self):
        spec = importlib.util.spec_from_file_location('round5_preflight_build', ROOT / 'scripts/build_release.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(dir=WORK) as folder:
            source = Path(folder) / 'source'; (source / 'config').mkdir(parents=True)
            shutil.copyfile(ROOT / 'pyproject.toml', source / 'pyproject.toml')
            (source / 'config/providers.example.json').write_text('{"providers":[{"enabled":true}]}', encoding='utf8')
            output = Path(folder) / 'release'
            with self.assertRaises(ValueError):
                module.build(source, output)
            self.assertEqual(list(output.glob('*.zip')), [])

    def test_git_ignore_covers_nonstandard_config_backups(self):
        with tempfile.TemporaryDirectory(dir=WORK) as folder:
            repo = Path(folder); shutil.copyfile(ROOT / '.gitignore', repo / '.gitignore')
            for name in ('config/providers.example.json', 'config/providers.mock.json', 'config/protocol-variants.example.json',
                         'config/providers.backup.json', 'config/key-store.json', 'config/secrets.private.json.bak', 'debug.log', 'session.db'):
                path = repo / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('synthetic', encoding='utf8')
            subprocess.run(['git', 'init', '-q'], cwd=repo, check=True, capture_output=True)
            subprocess.run(['git', 'add', '.'], cwd=repo, check=True, capture_output=True)
            tracked = subprocess.check_output(['git', 'ls-files'], cwd=repo, text=True).splitlines()
            self.assertEqual(set(tracked), {'.gitignore', 'config/providers.example.json', 'config/providers.mock.json', 'config/protocol-variants.example.json'})

if __name__ == '__main__': unittest.main()
