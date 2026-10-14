"""Build a redistributable node ZIP; never include credentials or runtime data."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import zipfile


RELEASE_FILES = frozenset("""
.gitattributes
h3_kontext_bridge/__init__.py
h3_kontext_bridge/nodes.py
h3_kontext_bridge/core-required-sha256.json
h3_kontext_bridge/requirements.txt
tests/test_h3k_delivery.py
docs/H3K-DELIVERY.md
docs/H3K-TARGET-PORTS.json
h3_background_bridge/__init__.py
h3_background_bridge/nodes.py
h3_background_bridge/adapter-required-sha256.json
workflows/H3_A2_API_ZImage_BackgroundCache_INTEGRATED.json
docs/RH-INTEGRATED-INSTALL.md
docs/INTEGRATED-WORKFLOW-NODES.json
docs/INTEGRATION-VALIDATION.md
tests/test_integrated_bridge.py
tests/test_independent_017.py
docs/AUDIT-017.md
.gitignore
LICENSE
README.md
SOURCE_MAP.md
FINAL_AUDIT_REPORT.md
CHANGELOG.md
RELEASE_CHECKLIST.md
__init__.py
config/protocol-variants.example.json
config/providers.example.json
config/providers.mock.json
docs/ARCHITECTURE.md
docs/AUDIT-ROUND2.md
docs/AUDIT-ROUND3.md
docs/AUDIT-ROUND4.md
docs/AUDIT-ROUND5.md
docs/AUDIT-ROUND5-FOLLOWUP.md
docs/CANDIDATE-EVIDENCE.md
docs/CHANGELOG.md
docs/GATEWAY-EVIDENCE.md
docs/HANDOVER.md
docs/PROTOCOLS.md
docs/REVIEW.md
docs/RUNNINGHUB.md
docs/TESTING.md
docs/THIRD-PARTY.md
docs/VALIDATION.md
examples/example_input.png
examples/image_edit_minimal.json
examples/image_edit_minimal_api.json
h3_adapter/__init__.py
h3_adapter/config.py
h3_adapter/engine.py
h3_adapter/ledger.py
h3_adapter/protocol.py
h3_adapter/routes.py
licenses/httpx-0-LICENSE.md
licenses/pillow-0-LICENSE
nodes.py
pyproject.toml
requirements-dev.txt
requirements.txt
scripts/build_release.py
scripts/mock_server.py
scripts/verify_comfyui.py
scripts/independent_http_smoke.py
tests/mock_api.py
tests/test_config.py
tests/test_development_upload.py
tests/test_development_frontend.mjs
tests/test_final_identity.py
tests/test_final_frontend.mjs
tests/test_followup_contracts.py
tests/test_engine.py
tests/test_frontend.mjs
tests/test_frontend_review.mjs
tests/test_ledger.py
tests/test_masks.py
tests/test_nodes.py
tests/test_protocol.py
tests/test_review.py
tests/test_round2_concurrency.py
tests/test_round2_config.py
tests/test_round2_images.py
tests/test_round2_release.py
tests/test_round2_scheduler.py
tests/test_round3_frontend.mjs
tests/test_round3_protocol.py
tests/test_round3_routes.py
tests/test_round3_state.py
tests/test_round4_credentials.py
tests/test_round4_frontend.mjs
tests/test_round4_health.py
tests/test_round4_parameters.py
tests/test_round4_recovery.py
tests/test_round4_release.py
tests/test_round5_contracts.py
tests/test_round5_release.py
tests/test_routes.py
web/h3_adapter.js
""".split())


def build(source, output):
    source = Path(source).resolve()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    version = re.search(r'(?m)^version\s*=\s*"([^"]+)"', (source / 'pyproject.toml').read_text(encoding='utf-8')).group(1)
    files = {name: (source / name).read_bytes() for name in sorted(RELEASE_FILES)
             if (source / name).is_file()}
    # Reject unsafe installation defaults before creating an archive.
    config = json.loads(files['config/providers.example.json'])
    if not all(p['enabled'] is False for p in config['providers']):
        raise ValueError('Release providers must start disabled')
    # Never package the user's active provider config; install starts from placeholders.
    files['config/providers.json'] = files['config/providers.example.json']
    manifest = {'version': version, 'files': [{'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()} for name, data in sorted(files.items())],
                'privacy': 'Exact release file allowlist; active provider settings replaced by disabled example',
                'verification': {'status': 'not_executed_by_package_builder', 'evidence': 'FINAL_AUDIT_REPORT.md'}}
    encoded = json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8')
    (source / 'SOURCE-MANIFEST.json').write_bytes(encoded)
    files['SOURCE-MANIFEST.json'] = encoded
    archive = output / f'ComfyUI-H3-Adapter-{version}.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in sorted(files.items()):
            z.writestr('ComfyUI-H3-Adapter/' + name, data)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for entry in manifest['files']:
            actual = z.read('ComfyUI-H3-Adapter/' + entry['path'])
            assert hashlib.sha256(actual).hexdigest() == entry['sha256']
        assert all('secrets.private' not in name and 'runtime.private/' not in name and '__pycache__/' not in name for name in z.namelist())
        config = json.loads(z.read('ComfyUI-H3-Adapter/config/providers.json'))
        assert all(p['enabled'] is False for p in config['providers'])
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / 'SHA256SUMS.txt').write_text(sha + '  ' + archive.name + '\n', encoding='utf-8')
    return {'path': str(archive), 'sha256': sha, 'archive_bytes': archive.stat().st_size, 'file_count': len(files)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument('--output', default=str(Path(__file__).resolve().parents[2] / 'releases'))
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output), ensure_ascii=False, indent=2))
