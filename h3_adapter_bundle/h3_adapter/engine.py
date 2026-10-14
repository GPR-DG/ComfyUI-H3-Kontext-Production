"""Small primary/backup scheduler with durable paid-submission state."""
from __future__ import annotations
import hashlib
import io
import json
import math
import os
import time
import uuid
from pathlib import Path
from PIL import Image, ImageOps
from .config import ConfigStore, ConfigError, ConfigConflict
from .ledger import Journal, JournalError
from .protocol import Protocol, APIError, _template_values


def fingerprint(images, mask, prompt, alias, provider, params, nonce):
    digest = hashlib.sha256(json.dumps([prompt, alias, provider, params, nonce], sort_keys=True, ensure_ascii=False, allow_nan=False).encode())
    for value in [*images, mask if mask is not None else b'']:
        digest.update(len(value).to_bytes(8, 'big'))
        digest.update(value)
    return digest.hexdigest()


def valid_image(content):
    if not isinstance(content, bytes) or not content or len(content) > 64 * 1024 * 1024:
        raise ValueError('invalid_image')
    with Image.open(io.BytesIO(content)) as image:
        if image.width * image.height > 40_000_000:
            raise ValueError('image_too_large')
        image.load()
        return image.size


def provider_mask(mask, model):
    if mask is None or model.get('mask_encoding', 'alpha_transparent_edit') != 'grayscale_white_edit':
        return mask
    with Image.open(io.BytesIO(mask)) as image:
        gray = ImageOps.invert(image.getchannel('A')) if 'A' in image.getbands() else image.convert('L')
        buffer = io.BytesIO()
        gray.save(buffer, format='PNG')
        return buffer.getvalue()


class Engine:
    def __init__(self, store: ConfigStore, runtime_dir: Path, protocol_factory=Protocol):
        self.store = store
        self.journal = Journal(runtime_dir)
        self.protocol_factory = protocol_factory

    def edit(self, images, mask=None, prompt='', model_alias='background-edit', provider='auto',
             auto_failover=True, params=None, timeout_seconds=120, max_cost=1.0, request_nonce=0):
        started = time.monotonic()
        report = {'request_id': '', 'status': 'failed', 'provider': None, 'model': None, 'error': None,
                  'elapsed_ms': 0, 'attempts': [], 'estimated_cost': None, 'currency': None, 'cached': False, 'warnings': []}
        def finish(status, error=None, output=None):
            report.update(status=status, error=error, elapsed_ms=round((time.monotonic() - started) * 1000))
            return {'images': output or [], 'report': report}
        try:
            cfg = self.store.load()
            if (params is not None and not isinstance(params, dict)) or not isinstance(prompt, str) or not prompt.strip():
                return finish('failed', 'invalid_prompt_or_parameters')
            params = params or {}
            if not isinstance(images, list) or not 1 <= len(images) <= 16:
                return finish('failed', 'invalid_image_count')
            size = valid_image(images[0])
            for image in images[1:]:
                valid_image(image)
            if mask is not None and valid_image(mask) != size:
                return finish('failed', 'mask_size_mismatch')
            if not isinstance(timeout_seconds, (int, float)) or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
                return finish('failed', 'invalid_timeout')
            if max_cost is not None and (not isinstance(max_cost, (int, float)) or not math.isfinite(max_cost) or max_cost < 0):
                return finish('failed', 'invalid_cost_limit')
            request_id = 'h3-' + fingerprint(images, mask, prompt, model_alias, provider, params, request_nonce)
            report['request_id'] = request_id
            report['currency'] = cfg.get('currency', 'USD')
            deadline = started + min(timeout_seconds, cfg.get('timeout_seconds', timeout_seconds))
            existing = self.journal.get(request_id)
            if existing is None and self.journal.has_legacy_submissions() and os.environ.get('H3_ADAPTER_ALLOW_LEGACY_NEW_REQUESTS') != '1':
                return finish('blocked', 'legacy_journal_new_request_requires_review')
            row = self.journal.begin(request_id, request_id)
            if row['state'] != 'ready':
                try:
                    self.store.authorize_snapshot(json.loads(row['snapshot']))
                except ConfigConflict:
                    return finish('awaiting_result' if row['state'] in ('accepted', 'result_ready') else 'blocked', 'credential_changed_no_resubmit')
            if row['state'] != 'ready' and row.get('currency') is not None:
                report['currency'] = row['currency']
            old_report = json.loads(row['report_json'])
            report['attempts'] = old_report.get('attempts', [])
            report['warnings'] = old_report.get('warnings', [])
            if row['state'] == 'completed':
                try:
                    output = [(self.journal.directory / p).read_bytes() for p in json.loads(row['result_files'])]
                    for content in output:
                        valid_image(content)
                    report.update(provider=row['provider'], model=row['model'], estimated_cost=json.loads(row['snapshot'])['model'].get('price_upper_bound'), cached=True)
                    return finish('success', output=output)
                except (OSError, ValueError):
                    return finish('blocked', 'cached_result_missing_no_resubmit')
            if row['state'] in ('submitting', 'uncertain'):
                report.update(provider=row['provider'], model=row['model'], estimated_cost=json.loads(row['snapshot'])['model'].get('price_upper_bound'))
                return finish('uncertain', 'previous_submission_unknown_no_resubmit')
            if row['state'] == 'failed':
                report.update(provider=row['provider'], model=row['model'], estimated_cost=json.loads(row['snapshot'])['model'].get('price_upper_bound'))
                return finish('failed', old_report.get('error', 'previous_terminal_failure_no_resubmit'))
            if row['state'] in ('accepted', 'result_ready'):
                snapshot = json.loads(row['snapshot'])
                return self._recover(request_id, row, snapshot, deadline, report, finish)
            available = {p['id']: p for p in cfg['providers']}
            if provider != 'auto':
                order = [provider]
            else:
                order = [cfg['primary']]
                if auto_failover and cfg.get('auto_failover', True):
                    order += sorted(cfg.get('fallbacks', []), key=lambda pid: available[pid].get('priority', 100))
            for pid in order:
                p = available.get(pid)
                m = p.get('models', {}).get(model_alias) if p else None
                health_identity = json.dumps([self.store.credential_identity(p),
                    getattr(cfg, 'credential_generations', {}).get(pid, 0)]) if p else None
                skip = None
                if not p or not p.get('enabled', True):
                    skip = 'provider_disabled_or_missing'
                elif not self.journal.available(pid, health_identity):
                    skip = 'provider_cooldown'
                elif not m or m.get('task') != 'image_edit' or len(images) > m.get('max_images', 1) or (mask is not None and not m.get('supports_mask', False)):
                    skip = 'incompatible_model_capability'
                elif set(params) - set(m.get('allowed_params', [])):
                    skip = 'unsupported_parameters'
                else:
                    cost = m.get('price_upper_bound')
                    if (max_cost is not None or cfg.get('max_total_cost') is not None) and cost is None:
                        skip = 'unknown_price_under_limit'
                    elif max_cost is not None and cost > max_cost:
                        skip = 'estimated_cost_exceeds_limit'
                    else:
                        key = self.store.credential(p, expected_revision=getattr(cfg, 'revision', None))
                        if not key:
                            skip = 'missing_server_key'
                if skip:
                    report['attempts'].append({'provider': pid, 'model': m.get('id') if m else None, 'status': 'skipped', 'error': skip, 'elapsed_ms': 0})
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return finish('no_provider', 'request_deadline_exceeded')
                effective = dict(m.get('defaults', {}))
                effective.update(params)
                # Never accept model/prompt/stream overrides through extra parameters.
                if any(k in effective for k in ('model', 'prompt', 'image', 'image[]', 'mask', 'stream')):
                    report['attempts'].append({'provider': pid, 'status': 'skipped', 'error': 'reserved_parameter', 'elapsed_ms': 0})
                    continue
                snapshot = {'identity_version': 2, 'provider': p, 'model': m, 'effective_params': effective,
                            'credential_fingerprint': self.store.credential_fingerprint(key),
                            'credential_generation': getattr(cfg, 'credential_generations', {}).get(pid, 0)}
                self.journal.reserve(request_id, pid, m['id'], snapshot, cost or 0, cfg.get('currency', 'USD'), cfg.get('max_total_cost'))
                warnings = []
                if p.get('protocol') == 'json_template':
                    used = set(_template_values((p.get('request') or {}).get('body', {})))
                    warnings = ['json_template_unmapped_' + name for name, token in
                                (('model', '{model}'), ('prompt', '{prompt}'), ('parameters', '{params}'))
                                if token not in used and (name != 'parameters' or effective)]
                report.update(provider=pid, model=m['id'], estimated_cost=cost, warnings=warnings)
                attempt = {'provider': pid, 'model': m['id'], 'status': 'submitting', 'error': None, 'elapsed_ms': 0}
                report['attempts'].append(attempt)
                self.journal.mark(request_id, 'submitting', report=report)
                api = None
                tick = time.monotonic()
                try:
                    api = self.protocol_factory(p, key)
                    prepared_mask = provider_mask(mask, m)
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise APIError('request_deadline_exceeded', safe_to_failover=True)
                    payload = api.submit(m, images, prepared_mask, prompt, effective, request_id, min(remaining, p.get('timeout_seconds', remaining)))
                    attempt.update(status='accepted', elapsed_ms=round((time.monotonic() - tick) * 1000))
                    if p.get('async'):
                        task = api.task_id(payload)
                        if not task:
                            raise APIError('missing_task_id', uncertain=True)
                        self.journal.mark(request_id, 'accepted', task_id=task, report=report)
                    else:
                        self.journal.mark(request_id, 'result_ready', result=api.result_record(payload), report=report)
                except APIError as error:
                    attempt.update(status='rejected' if error.safe_to_failover else 'uncertain', error=error.code,
                                   elapsed_ms=round((time.monotonic() - tick) * 1000))
                    if error.safe_to_failover:
                        self.journal.reject(request_id, report)
                        if error.provider_failure:
                            self.journal.cooldown(pid, cfg.get('cooldown_seconds', 60), health_identity)
                        continue
                    self.journal.mark(request_id, 'uncertain', report=report)
                    return finish('uncertain', error.code)
                except Exception:
                    attempt.update(status='uncertain', error='unexpected_submission_error')
                    self.journal.mark(request_id, 'uncertain', report=report)
                    return finish('uncertain', 'unexpected_submission_error')
                finally:
                    if api is not None:
                        api.close()
                return self._recover(request_id, self.journal.get(request_id), snapshot, deadline, report, finish)
            return finish('no_provider', 'no_eligible_provider')
        except ConfigError:
            return finish('failed', 'invalid_provider_config')
        except JournalError:
            return finish('blocked', 'journal_claim_or_budget_denied')
        except (ValueError, TypeError, OSError):
            return finish('failed', 'invalid_input_or_storage')

    def _recover(self, request_id, row, snapshot, deadline, report, finish):
        p = snapshot['provider']
        report.update(provider=row['provider'], model=row['model'], estimated_cost=snapshot['model'].get('price_upper_bound'))
        api = None
        try:
            locator = json.loads(row['result_json']).get('_h3_result', {}) if row['state'] == 'result_ready' else None
            key = '' if locator is not None and not Protocol.result_requires_key(p, locator) else self.store.credential(
                p, recovery=True, expected_fingerprint=snapshot.get('credential_fingerprint'),
                expected_generation=snapshot.get('credential_generation'))
            api = self.protocol_factory(p, key)
            if row['state'] == 'accepted':
                config = p.get('async', {})
                polls = config.get('max_polls', 120)
                for _ in range(polls):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return finish('awaiting_result', 'poll_deadline_no_resubmit')
                    state, payload = api.poll(row['task_id'], min(remaining, p.get('timeout_seconds', remaining)))
                    if state == 'failed':
                        finish('failed', 'remote_task_failed_no_resubmit')
                        self.journal.mark(request_id, 'failed', report=report)
                        row = self.journal.get(request_id)
                        break
                    if state == 'succeeded':
                        self.journal.mark(request_id, 'result_ready', result=api.result_record(payload), report=report)
                        row = self.journal.get(request_id)
                        break
                    time.sleep(min(max(0, config.get('poll_interval', 1)), max(0, deadline - time.monotonic())))
                else:
                    return finish('awaiting_result', 'poll_limit_no_resubmit')
            if row['state'] == 'completed':
                try:
                    output = [(self.journal.directory / p).read_bytes() for p in json.loads(row['result_files'])]
                    for content in output:
                        valid_image(content)
                except (OSError, ValueError):
                    return finish('blocked', 'cached_result_missing_no_resubmit')
                report['cached'] = True
                return finish('success', output=output)
            if row['state'] == 'failed':
                return finish('failed', 'remote_task_failed_no_resubmit')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return finish('awaiting_result', 'download_deadline_no_resubmit')
            output = api.result(json.loads(row['result_json']), remaining)
            names, normalized = [], []
            for i, content in enumerate(output):
                valid_image(content)
                normalized.append(content)
                name = f'{request_id}-{i}.image'
                target = self.journal.directory / name
                temp = target.with_name(target.name + '.' + uuid.uuid4().hex + '.tmp')
                try:
                    temp.write_bytes(normalized[-1])
                    temp.replace(target)
                finally:
                    temp.unlink(missing_ok=True)
                names.append(name)
            if not names:
                return finish('awaiting_result', 'empty_result_no_resubmit')
            finish('success', output=normalized)
            self.journal.mark(request_id, 'completed', files=names, report=report)
            return {'images': normalized, 'report': report}
        except ConfigConflict:
            return finish('awaiting_result', 'credential_changed_no_resubmit')
        except APIError as error:
            return finish('awaiting_result', error.code)
        except Exception:
            return finish('awaiting_result', 'invalid_result_or_storage_no_resubmit')
        finally:
            if api is not None:
                api.close()
