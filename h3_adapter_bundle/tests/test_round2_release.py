"""The builder must not fabricate test results or silently pin another source version."""
import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

class ReleaseTests(unittest.TestCase):
    def build_fixture(self):
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location("h3_round2_builder",root/"scripts/build_release.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        folder=tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        source=Path(folder.name)/"source"
        source.mkdir()
        (source/"config").mkdir()
        (source/"pyproject.toml").write_text('[project]\nname="fixture"\nversion = "9.8.7"\n',encoding="utf-8")
        (source/"config/providers.example.json").write_text('{"providers":[{"enabled":false}]}',encoding="utf-8")
        (source/".env").write_text("H3_PROVIDER_KEY=SYNTHETIC-DOTENV-KEY",encoding="utf-8")
        (source/"private.env").write_text("KEY=SYNTHETIC-ENV-FILE",encoding="utf-8")
        (source/".env.production").write_text("KEY=SYNTHETIC-PRODUCTION-KEY",encoding="utf-8")
        (source/"config/providers.json").write_text('{"providers":[{"enabled":true}]}',encoding="utf-8")
        return module.build(source,Path(folder.name)/"release"),source

    def test_archive_version_matches_packaged_project(self):
        result, source=self.build_fixture()
        self.assertEqual(Path(result["path"]).name,"ComfyUI-H3-Adapter-9.8.7.zip")
        manifest=json.loads((source/"SOURCE-MANIFEST.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"],"9.8.7")

    def test_package_build_does_not_assert_unexecuted_tests_passed(self):
        result,source=self.build_fixture()
        manifest=json.loads((source/"SOURCE-MANIFEST.json").read_text(encoding="utf-8"))
        self.assertNotIn("passed",manifest.get("verification",{}),"Builder never ran a test; fixed green counts are fabricated")
        self.assertNotIn("failed",manifest.get("verification",{}))
        with zipfile.ZipFile(result["path"]) as archive:
            data=json.loads(archive.read("ComfyUI-H3-Adapter/config/providers.json"))
            self.assertFalse(data["providers"][0]["enabled"])

    def test_environment_credential_files_are_never_archived(self):
        result,source=self.build_fixture()
        with zipfile.ZipFile(result["path"]) as archive:
            names=archive.namelist()
            for name in (".env","private.env",".env.production"):
                self.assertNotIn("ComfyUI-H3-Adapter/"+name,names)
            self.assertNotIn(b"SYNTHETIC-DOTENV-KEY",b"".join(archive.read(n) for n in names))

if __name__=="__main__":
    unittest.main()
