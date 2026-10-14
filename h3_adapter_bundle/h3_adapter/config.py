"""Non-secret configuration and server-side credentials; no workflow secrets."""
from contextlib import contextmanager
import uuid
import hashlib
import json
import math
import os
import re
from pathlib import Path
from urllib.parse import urlsplit


class ConfigError(ValueError):
    pass


class ConfigConflict(ConfigError):
    pass


def atomic_json(path, value, private=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('w', encoding='utf-8') as f:
            if private:
                os.chmod(temporary, 0o600)
            json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
        if private:
            os.chmod(path, 0o600)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def settings_lock(path):
    """Serialize secret read-modify-write across Comfy worker processes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as lock:
        if lock.tell() == 0:
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == 'nt':
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def validate(config):
    if not isinstance(config, dict) or config.get('version') != 1:
        raise ConfigError('Configuration version must be 1')
    providers = config.get('providers')
    if not isinstance(providers, list) or not providers:
        raise ConfigError('At least one provider is required')
    ids = []
    for p in providers:
        if not isinstance(p, dict) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', p.get('id', '')):
            raise ConfigError('Provider id must contain only letters, digits, underscore or hyphen')
        ids.append(p['id'])
        for obj in ('async', 'request', 'result', 'upload', 'auth'):
            if p.get(obj) is not None and not isinstance(p[obj], dict):
                raise ConfigError(obj + ' configuration must be an object or null')
        for name, default in [('timeout_seconds', 120), ('max_response_bytes', 67108864), ('priority', 100)]:
            value = p.get(name, default)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ConfigError(name + ' must be positive and finite')
        limit = p.get('max_response_bytes', 67108864)
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ConfigError('max_response_bytes must be a positive integer')
        if p.get('async'):
            a = p['async']
            if isinstance(a.get('max_polls', 120), bool) or not isinstance(a.get('max_polls', 120), int) or not 1 <= a.get('max_polls', 120) <= 10000:
                raise ConfigError('Async max_polls must be 1..10000')
            interval = a.get('poll_interval', 1)
            if isinstance(interval, bool) or not isinstance(interval, (int, float)) or not math.isfinite(interval) or interval < 0:
                raise ConfigError('Async poll_interval must be nonnegative finite')
            success, failure = a.get('success', ['succeeded']), a.get('failure', ['failed'])
            if any(not isinstance(states, list) or any(not isinstance(state, str) or not state for state in states) for states in (success, failure)) or set(success) & set(failure):
                raise ConfigError('Async success/failure must be disjoint string lists')
            if any(not isinstance(a.get(name), str) or not a[name] for name in ('task_id_path', 'poll_path', 'status_path')) or '{task_id}' not in a['poll_path']:
                raise ConfigError('Async task/status paths and {task_id} poll placeholder are required')

        if not isinstance(p.get('enabled', True), bool) or not isinstance(p.get('allow_insecure_localhost', False), bool):
            raise ConfigError('enabled/loopback flags must be booleans')
        if not isinstance(p.get('base_url'), str):
            raise ConfigError('Base URL must be a string')
        try:
            url = urlsplit(p['base_url'])
            url.port
        except ValueError:
            raise ConfigError('Invalid Base URL or port') from None
        local_http = url.scheme == 'http' and url.hostname in ('localhost', '127.0.0.1', '::1') and p.get('allow_insecure_localhost') is True
        if not url.hostname or (url.scheme != 'https' and not local_http) or url.username or url.password or url.query or url.fragment:
            raise ConfigError('Base URL requires HTTPS without credentials/query; only explicit loopback mocks allow HTTP')
        if p.get('protocol') not in ('openai_images', 'json_template'):
            raise ConfigError('Supported protocols: openai_images, json_template')
        for path in [p.get('edit_path')] + [obj.get('path') for obj in (p.get('discovery'), p.get('upload')) if isinstance(obj, dict)] + ([p['async'].get('poll_path')] if p.get('async') else []):
            if not isinstance(path, str) or not path.startswith('/') or path.startswith('//') or '..' in path.split('/') or urlsplit(path).scheme:
                raise ConfigError('Endpoint paths must be explicit relative /paths, appended to Base URL')
        if 'account_id' in p and (not isinstance(p['account_id'], str) or not p['account_id'].strip() or len(p['account_id']) > 128):
            raise ConfigError('account_id must be a non-secret stable account label, at most 128 characters')
        env = p.get('key_env', '')
        if not isinstance(env, str) or (env and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', env)):
            raise ConfigError('Invalid key environment-variable name')
        if any(k in p for k in ('api_key', 'key', 'token', 'headers')):
            raise ConfigError('Plaintext credentials/headers are not allowed in shared config; use key_env or secret manager')
        auth = p.get('auth') or {'header': 'Authorization', 'prefix': 'Bearer '}
        if set(auth) - {'header', 'prefix'} or any(not isinstance(v, str) or '\n' in v or '\r' in v for v in auth.values()) or not re.fullmatch(r'[A-Za-z0-9-]+', auth.get('header', 'Authorization')):
            raise ConfigError('Auth config only allows header name and prefix')
        models = p.get('models')
        if not isinstance(models, dict) or not models:
            raise ConfigError('Each provider requires a manual logical model mapping')
        for alias, m in models.items():
            if not isinstance(alias, str) or not alias or not isinstance(m, dict) or not isinstance(m.get('id'), str) or not m['id']:
                raise ConfigError('Model alias and actual id must be nonempty strings')
            if m.get('task') != 'image_edit' or not isinstance(m.get('supports_mask', False), bool):
                raise ConfigError('This phase supports only declared image_edit capabilities')
            if not isinstance(m.get('max_images', 1), int) or not 1 <= m.get('max_images', 1) <= 16:
                raise ConfigError('max_images must be 1..16')
            if m.get('mask_encoding', 'alpha_transparent_edit') not in ('alpha_transparent_edit', 'grayscale_white_edit'):
                raise ConfigError('Unsupported declared mask encoding')
            cost = m.get('price_upper_bound')
            if cost is not None and (isinstance(cost, bool) or not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost < 0):
                raise ConfigError('price_upper_bound must be a nonnegative finite estimate or null')
            if not isinstance(m.get('allowed_params', []), list) or any(not isinstance(name, str) for name in m.get('allowed_params', [])) or not isinstance(m.get('defaults', {}), dict):
                raise ConfigError('Model defaults/allowed_params must be object/string list')
        codes = p.get('safe_reject_statuses', [401, 403, 404])
        if not isinstance(codes, list) or any(not isinstance(c, int) or not 400 <= c < 500 for c in codes):
            raise ConfigError('safe_reject_statuses must be HTTP 4xx codes with documented non-acceptance; 5xx always uncertain')
        discovery = p.get('discovery')
        if discovery is not None and not isinstance(discovery, dict):
            raise ConfigError('discovery must be null or an explicit API definition')
    if len(ids) != len(set(ids)) or config.get('primary') not in ids:
        raise ConfigError('Provider ids must be unique and primary must exist')
    fallbacks = config.get('fallbacks', [])
    if not isinstance(fallbacks, list) or len(fallbacks) != len(set(fallbacks)) or any(x not in ids or x == config['primary'] for x in fallbacks):
        raise ConfigError('Fallback ids must exist, be unique, and differ from primary')
    if not isinstance(config.get('currency', 'USD'), str):
        raise ConfigError('Currency must be a common unit for all estimates')
    if not isinstance(config.get('auto_failover', True), bool):
        raise ConfigError('auto_failover must be a boolean')
    for name, default in [('timeout_seconds', 120), ('cooldown_seconds', 60), ('max_total_cost', None)]:
        value = config.get(name, default)
        if value is None and name != 'max_total_cost':
            raise ConfigError(name + ' must be finite and nonnegative (timeout positive)')
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or (name == 'timeout_seconds' and value == 0)):
            raise ConfigError(name + ' must be finite and nonnegative (timeout positive)')
    return config


class _ConfigSnapshot(dict):
    """Dictionary-compatible config with a non-serialized read revision."""
    pass


class ConfigStore:
    def __init__(self, path):
        self.path = Path(path)
        self.secret_path = self.path.with_name('secrets.private.json')

    def load(self):
        with settings_lock(self.path.with_name('.settings.lock')):
            config = _ConfigSnapshot(self._load())
            config.revision = self.revision(config)
            config.credential_generations = self.credential_generations(config)
            return config

    def _load(self):
        try:
            return validate(json.loads(self.path.read_text(encoding='utf-8-sig')))
        except (OSError, json.JSONDecodeError):
            raise ConfigError('Missing/invalid provider config; copy providers.example.json to providers.json') from None

    def credential_generations(self, config):
        try:
            secrets = json.loads(self.secret_path.read_text(encoding='utf-8-sig'))
        except (OSError, json.JSONDecodeError):
            secrets = {}
        return {p['id']: entry.get('generation', 0) if isinstance(entry := secrets.get(p['id']), dict) else 0
                for p in config['providers']}

    def revision(self, config):
        try:
            secrets = json.loads(self.secret_path.read_text(encoding='utf-8-sig'))
        except (OSError, json.JSONDecodeError):
            secrets = {}
        epochs = {p['id']: entry['generation'] for p in config['providers']
                  if isinstance(entry := secrets.get(p['id']), dict) and entry.get('generation')}
        value = [config, epochs] if epochs else config
        return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()

    def save(self, config, expected_revision=None):
        config = validate(config)
        if expected_revision is not None and not isinstance(expected_revision, str):
            raise ConfigError('Invalid configuration revision')
        # Same cross-process lock as keys; check and replace must be one operation.
        with settings_lock(self.path.with_name('.settings.lock')):
            if expected_revision is not None and expected_revision != self.revision(self._load()):
                raise ConfigConflict('Configuration changed; reload before saving')
            previous = self._load() if self.path.exists() else {'providers': []}
            removed = {p['id'] for p in previous['providers']} - {p['id'] for p in config['providers']}
            if removed:
                try:
                    secrets = json.loads(self.secret_path.read_text(encoding='utf-8-sig'))
                except FileNotFoundError:
                    secrets = {}
                for pid in removed:
                    entry = secrets.get(pid, '')
                    if isinstance(entry, str):
                        entry = {'key': entry, 'retired': []}
                    if entry.get('key'):
                        entry.setdefault('retired', []).append(entry['key'])
                    entry['key'] = ''
                    entry['generation'] = entry.get('generation', 0) + 1
                    secrets[pid] = entry
                # Retire before publishing removal: failure may block new work, never reuse an old key.
                atomic_json(self.secret_path, secrets, private=True)
            atomic_json(self.path, config)
            return self.revision(config)

    def key(self, provider):
        value = os.environ.get(provider.get('key_env', ''), '')
        if value:
            return value
        try:
            secrets = json.loads(self.secret_path.read_text(encoding='utf-8-sig'))
            entry = secrets.get(provider['id'], '')
            return entry.get('key', '') if isinstance(entry, dict) else entry
        except (OSError, json.JSONDecodeError):
            return ''

    @staticmethod
    def credential_identity(provider):
        auth = provider.get('auth') or {}
        return (provider['base_url'].rstrip('/'), provider.get('key_env', ''),
                auth.get('header', 'Authorization').lower(), auth.get('prefix', 'Bearer '), provider.get('account_id'))

    @staticmethod
    def credential_fingerprint(key):
        return hashlib.sha256(key.encode('utf-8')).hexdigest()

    def credential(self, provider, *, recovery=False, expected_fingerprint=None, expected_revision=None, expected_generation=None):
        # Capture one coherent endpoint/key pair; old tasks never borrow a new merchant's key.
        with settings_lock(self.path.with_name('.settings.lock')):
            config = self._load()
            if not recovery and expected_revision is not None and expected_revision != self.revision(config):
                raise ConfigConflict('Configuration changed before credential capture')
            current = next((p for p in config['providers'] if p['id'] == provider['id']), None)
            same = current is not None and self.credential_identity(current) == self.credential_identity(provider)
            key = self.key(provider)
            same_generation = True
            if recovery:
                try:
                    entry = json.loads(self.secret_path.read_text(encoding='utf-8-sig')).get(provider['id'], {})
                except (OSError, json.JSONDecodeError):
                    entry = {}
                generation = entry.get('generation', 0) if isinstance(entry, dict) else 0
                same_generation = generation == (expected_generation if expected_generation is not None else 0)
                proven_key = bool(key and expected_fingerprint and self.credential_fingerprint(key) == expected_fingerprint)
                declared_account = bool(provider.get('account_id') and same)
                if same and same_generation and isinstance(key, str) and key and (proven_key or declared_account):
                    return key
                retired = entry.get('retired', []) if isinstance(entry, dict) else []
                if isinstance(entry, dict) and entry.get('generation') and not expected_fingerprint:
                    raise ConfigConflict('Legacy task cannot identify a retired credential')
                for old_key in retired:
                    if expected_fingerprint and self.credential_fingerprint(old_key) == expected_fingerprint:
                        return old_key
            if not isinstance(key, str):
                raise ConfigError('Invalid credential')
            matches = bool(key and expected_fingerprint and self.credential_fingerprint(key) == expected_fingerprint)
            if (not recovery and not same) or (recovery and (not key or not ((same and same_generation and provider.get('account_id')) or matches))):
                raise ConfigConflict('Provider credential identity changed; restore the original configuration and key')
            return key

    def authorize_snapshot(self, snapshot):
        """Authorize cache/recovery before reading private results; never submit here."""
        provider = snapshot['provider']
        with settings_lock(self.path.with_name('.settings.lock')):
            config = self._load()
            current = next((p for p in config['providers'] if p['id'] == provider['id']), None)
            # A missing slot is not authorization: an unrelated configuration may
            # share this journal. Only the original key (including retired keys)
            # can consume a deleted slot's private result.
            key = self.key(current if current is not None else provider)
            expected = snapshot.get('credential_fingerprint')
            if key and expected and self.credential_fingerprint(key) == expected:
                return
            if not key and expected:
                try:
                    entry = json.loads(self.secret_path.read_text(encoding='utf-8-sig')).get(provider['id'], {})
                except (OSError, json.JSONDecodeError):
                    entry = {}
                if isinstance(entry, dict) and any(self.credential_fingerprint(old) == expected for old in entry.get('retired', [])):
                    return
            same_account = bool(current is not None and provider.get('account_id') and self.credential_identity(current) == self.credential_identity(provider))
            generation = self.credential_generations(config).get(provider['id'], 0)
            if key and same_account and generation == snapshot.get('credential_generation', 0):
                return
            raise ConfigConflict('Account changed; private cached results and old tasks require their original account')

    def save_key(self, provider_id, key, expected_revision=None):
        if not isinstance(key, str) or '\n' in key or '\r' in key or len(key) > 8192:
            raise ConfigError('Invalid credential')
        if expected_revision is not None and not isinstance(expected_revision, str):
            raise ConfigError('Invalid configuration revision')
        with settings_lock(self.path.with_name('.settings.lock')):
            config = self._load()
            if expected_revision is not None and expected_revision != self.revision(config):
                raise ConfigConflict('Configuration changed; reload before saving a key')
            if provider_id not in {p['id'] for p in config['providers']}:
                raise ConfigError('Unknown provider')
            try:
                secrets = json.loads(self.secret_path.read_text(encoding='utf-8-sig'))
            except (OSError, json.JSONDecodeError):
                secrets = {}
            entry = secrets.get(provider_id)
            if isinstance(entry, dict):
                entry['key'] = key
            elif key:
                secrets[provider_id] = key
            else:
                secrets.pop(provider_id, None)
            atomic_json(self.secret_path, secrets, private=True)

    def public(self):
        with settings_lock(self.path.with_name('.settings.lock')):
            config = self._load()
            return {'config': config, 'revision': self.revision(config), 'keys': {p['id']: bool(self.key(p)) for p in config['providers']}}
