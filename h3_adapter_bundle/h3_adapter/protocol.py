"""Single-attempt provider protocols. The engine owns failover and job recovery."""
from __future__ import annotations

import base64
import binascii
import json
import zlib
from time import monotonic
from urllib.parse import quote, urlsplit

import httpx


class APIError(Exception):
    def __init__(self, code: str, *, safe_to_failover: bool = False, uncertain: bool = False, provider_failure: bool = False):
        self.code = code
        self.safe_to_failover = safe_to_failover
        self.uncertain = uncertain
        self.provider_failure = provider_failure
        # Never attach provider bodies, keys, signed URLs or exception messages.
        super().__init__("Provider operation failed.")


def _path(payload, path):
    value = payload
    if not isinstance(path, str) or not path:
        return None
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return None
    return value


def _render(value, tokens):
    if isinstance(value, dict):
        return {key: _render(item, tokens) for key, item in value.items()}
    if isinstance(value, list):
        return [_render(item, tokens) for item in value]
    return tokens.get(value, value) if isinstance(value, str) else value


def _template_values(value):
    if isinstance(value, (dict, list)):
        for item in value.values() if isinstance(value, dict) else value:
            yield from _template_values(item)
    elif isinstance(value, str):
        yield value


def _multipart_field(value):
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise APIError("invalid_multipart_field", safe_to_failover=True)
    return value


class Protocol:
    def __init__(self, provider: dict, key: str, transport=None):
        self.provider = provider
        self.key = key
        self.base_url = provider.get("base_url", "").rstrip("/")
        try:
            parsed = urlsplit(self.base_url)
            permitted_http = (
                parsed.scheme == "http" and provider.get("allow_insecure_localhost") is True
                and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            )
            if (parsed.scheme != "https" and not permitted_http) or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError
            parsed.port
        except (ValueError, TypeError):
            raise APIError("invalid_base_url", safe_to_failover=True) from None
        self.api_origin = (parsed.scheme, parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
        self.max_response_bytes = provider.get("max_response_bytes", 64 * 1024 * 1024)
        if isinstance(self.max_response_bytes, bool) or not isinstance(self.max_response_bytes, int) or self.max_response_bytes < 1:
            raise APIError("invalid_response_limit", safe_to_failover=True)
        self.client = httpx.Client(
            transport=transport if transport is not None else httpx.HTTPTransport(retries=0, verify=True, trust_env=False),
            verify=True, trust_env=False, follow_redirects=False,
        )

    def close(self):
        self.client.close()

    def _url(self, path):
        if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
            raise APIError("invalid_endpoint", safe_to_failover=True)
        return self.base_url + path

    def _headers(self):
        auth = self.provider.get("auth") or {}
        header = auth.get("header", "Authorization")
        if not self.key or not header:
            return {}
        try:
            value = auth.get("prefix", "Bearer ") + self.key
            value.encode("ascii")
            if "\r" in value or "\n" in value or "\x00" in value or value.startswith((" ", "\t")) or value.endswith((" ", "\t")):
                raise ValueError
        except (TypeError, ValueError, UnicodeError):
            raise APIError("invalid_auth_header", safe_to_failover=True) from None
        return {header: value}

    @staticmethod
    def _remaining(deadline, *, submitted=False):
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise APIError("submit_deadline_exceeded", safe_to_failover=not submitted, uncertain=submitted)
        return remaining

    def _bounded_content(self, response, deadline):
        # Real network streams use iter_raw: HTTPX must not inflate before our cap.
        if response.is_stream_consumed:
            # Eager in-memory MockTransport responses have already been materialized.
            if len(response.content) > self.max_response_bytes:
                raise APIError('response_too_large', uncertain=True)
            return response.content
        encoding = response.headers.get('content-encoding', 'identity').strip().lower()
        if encoding not in ('', 'identity', 'gzip', 'deflate'):
            raise APIError('unsupported_response_encoding', uncertain=True)
        compressed = encoding in ('gzip', 'deflate')
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS) if encoding == 'gzip' else None
        content, wire, prefix = bytearray(), 0, b''
        for chunk in response.iter_raw():
            if deadline is not None:
                self._remaining(deadline, submitted=True)
            wire += len(chunk)
            if wire > self.max_response_bytes:
                raise APIError('response_too_large', uncertain=True)
            if not compressed:
                content.extend(chunk)
                continue
            if encoding == 'deflate' and decoder is None:
                prefix += chunk
                if len(prefix) < 2:
                    continue
                zlib_header = prefix[0] & 15 == 8 and (prefix[0] * 256 + prefix[1]) % 31 == 0
                decoder = zlib.decompressobj(zlib.MAX_WBITS if zlib_header else -zlib.MAX_WBITS)
                chunk, prefix = prefix, b''
            while chunk:
                if decoder.eof:
                    if encoding != 'gzip':
                        raise APIError('invalid_response_compression', uncertain=True)
                    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
                block = decoder.decompress(chunk, min(65536, self.max_response_bytes - len(content) + 1))
                if len(content) + len(block) > self.max_response_bytes:
                    raise APIError('response_too_large', uncertain=True)
                content.extend(block)
                chunk = decoder.unused_data if decoder.eof else decoder.unconsumed_tail
                if deadline is not None:
                    self._remaining(deadline, submitted=True)
        if compressed and (decoder is None or not decoder.eof):
            raise APIError('invalid_response_compression', uncertain=True)
        return bytes(content)

    def _request(self, method, url, timeout, *, headers=None, submission=False, deadline=None, **kwargs):
        if deadline is not None:
            timeout = min(timeout, self._remaining(deadline))
        try:
            request_headers = dict(self._headers() if headers is None else headers)
            request_headers['Accept-Encoding'] = 'gzip, deflate'
            with self.client.stream(method, url, headers=request_headers, timeout=httpx.Timeout(timeout), **kwargs) as response:
                if not 200 <= response.status_code < 300:
                    safe = submission and 400 <= response.status_code < 500 and response.status_code in self.provider.get("safe_reject_statuses", [401, 403, 404])
                    raise APIError("http_rejected" if safe else "http_uncertain", safe_to_failover=safe, uncertain=not safe, provider_failure=safe)
                if deadline is not None:
                    self._remaining(deadline, submitted=True)
                content = self._bounded_content(response, deadline)
                return httpx.Response(response.status_code, content=content)
        except APIError:
            raise
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as error:
            raise APIError("request_not_sent", safe_to_failover=submission, uncertain=not submission,
                           provider_failure=not isinstance(error, httpx.PoolTimeout)) from None
        except Exception:
            # ponytail: no POST retry; the peer may already have accepted the job.
            raise APIError("transport_uncertain", uncertain=True) from None

    def _json_request(self, method, path, timeout, *, submission=False, **kwargs):
        response = self._request(method, self._url(path), timeout, submission=submission, **kwargs)
        try:
            payload = response.json()
        except (ValueError, UnicodeError):
            raise APIError("invalid_json", uncertain=True) from None
        if not isinstance(payload, dict):
            raise APIError("invalid_json", uncertain=True)
        return payload

    def _upload(self, content, name, timeout, deadline):
        upload = self.provider.get("upload") or {}
        payload = self._json_request(
            "POST", upload.get("path"), timeout, submission=True, deadline=deadline,
            files={_multipart_field(upload.get("field", "file")): (name, content, "image/png")},
        )
        reference = _path(payload, upload.get("ref_path", "url"))
        if not isinstance(reference, str) or not reference:
            raise APIError("invalid_upload_reference", uncertain=True)
        return reference

    def submit(self, model: dict, images: list[bytes], mask: bytes | None, prompt: str, params: dict, request_id: str, timeout: float) -> dict:
        deadline = monotonic() + timeout
        if not images or not all(isinstance(image, bytes) and image for image in images):
            raise APIError("invalid_images", safe_to_failover=True)
        request = self.provider.get("request") or {}
        protocol = self.provider.get("protocol")
        path = self.provider.get("edit_path")
        self._url(path)
        if protocol == "openai_images":
            fields = {key: value if isinstance(value, str) else json.dumps(value, separators=(",", ":")) for key, value in params.items() if value is not None}
            fields.update(model=model["id"], prompt=prompt)
            image_field = _multipart_field(request.get("image_field", "image"))
            files = [(image_field, (f"image_{index}.png", image, "image/png")) for index, image in enumerate(images)]
            if mask is not None:
                files.append((_multipart_field(request.get("mask_field", "mask")), ("mask.png", mask, "image/png")))
            return self._json_request("POST", path, timeout, submission=True, deadline=deadline, data=fields, files=files)
        if protocol != "json_template" or not isinstance(request.get("body"), dict):
            raise APIError("invalid_protocol", safe_to_failover=True)
        used = set(_template_values(request["body"]))
        if not used & {"{images_data_urls}", "{image_data_url}", "{image_base64}", "{image_ref}"}:
            raise APIError("unmapped_images", safe_to_failover=True)
        if len(images) > 1 and "{images_data_urls}" not in used:
            raise APIError("template_single_image_only", safe_to_failover=True)
        if mask is not None and not used & {"{mask_data_url}", "{mask_base64}", "{mask_ref}"}:
            raise APIError("unmapped_mask", safe_to_failover=True)
        if used & {"{image_ref}", "{mask_ref}"}:
            if not self.provider.get("upload"):
                raise APIError("missing_upload_config", safe_to_failover=True)
            if len(images) != 1:
                raise APIError("upload_single_image_only", safe_to_failover=True)
        image_b64 = [base64.b64encode(image).decode("ascii") for image in images]
        mask_b64 = base64.b64encode(mask).decode("ascii") if mask is not None else None
        tokens = {
            "{model}": model["id"], "{prompt}": prompt, "{params}": params,
            "{images_data_urls}": ["data:image/png;base64," + image for image in image_b64],
            "{image_data_url}": "data:image/png;base64," + image_b64[0], "{image_base64}": image_b64[0],
            "{mask_data_url}": "data:image/png;base64," + mask_b64 if mask_b64 is not None else None,
            "{mask_base64}": mask_b64,
        }
        if "{image_ref}" in used:
            tokens["{image_ref}"] = self._upload(images[0], "image.png", timeout, deadline)
        if "{mask_ref}" in used:
            tokens["{mask_ref}"] = self._upload(mask, "mask.png", timeout, deadline) if mask is not None else None
        return self._json_request("POST", path, timeout, submission=True, deadline=deadline, json=_render(request["body"], tokens))

    def task_id(self, payload: dict) -> str | None:
        config = self.provider.get("async") or {}
        value = _path(payload, config.get("task_id_path"))
        if value is None:
            return None
        if isinstance(value, int) and not isinstance(value, bool):
            value = str(value)
        if not isinstance(value, str) or not value.strip() or len(value) > 1024 or any(ord(character) < 32 for character in value) or (self.key and self.key in value):
            raise APIError("invalid_task_id", uncertain=True)
        return value

    def poll(self, task_id: str, timeout: float) -> tuple[str, dict]:
        config = self.provider.get("async") or {}
        template = config.get("poll_path")
        if not isinstance(template, str) or "{task_id}" not in template or not isinstance(task_id, str) or not task_id:
            raise APIError("invalid_task", uncertain=True)
        payload = self._json_request("GET", template.replace("{task_id}", quote(task_id, safe="")), timeout, deadline=monotonic() + timeout)
        status = _path(payload, config.get("status_path"))
        if not isinstance(status, str):
            raise APIError("invalid_task_status", uncertain=True)
        if status in config.get("success", ["succeeded"]):
            return "succeeded", payload
        if status in config.get("failure", ["failed"]):
            return "failed", payload
        return "pending", payload

    def result_record(self, payload: dict) -> dict:
        canonical = payload.get("_h3_result") if isinstance(payload, dict) else None
        config = self.provider.get("result") or {}
        b64 = canonical.get("b64") if isinstance(canonical, dict) else _path(payload, config.get("b64_path", "data.0.b64_json"))
        if isinstance(b64, str) and b64:
            return {"_h3_result": {"b64": b64}}
        url = canonical.get("url") if isinstance(canonical, dict) else _path(payload, config.get("url_path", "data.0.url"))
        if isinstance(url, str) and url:
            return {"_h3_result": {"url": url}}
        raise APIError("missing_result", uncertain=True)

    @staticmethod
    def result_requires_key(provider, locator):
        if "b64" in locator or (provider.get("result") or {}).get("download_auth") is not True:
            return False
        origin = lambda url: (url.scheme, url.hostname, url.port or (443 if url.scheme == "https" else 80))
        return origin(urlsplit(locator["url"])) == origin(urlsplit(provider["base_url"]))

    def result(self, payload: dict, timeout: float) -> list[bytes]:
        locator = self.result_record(payload)["_h3_result"]
        if "b64" in locator:
            if len(locator["b64"]) > 4 * ((self.max_response_bytes + 2) // 3):
                raise APIError("response_too_large", uncertain=True)
            try:
                data = base64.b64decode(locator["b64"], validate=True)
            except (ValueError, binascii.Error):
                raise APIError("invalid_result_base64", uncertain=True) from None
        else:
            url = locator["url"]
            config = self.provider.get("result") or {}
            try:
                parsed = urlsplit(url)
                permitted_http = (
                    parsed.scheme == "http" and self.provider.get("allow_insecure_localhost") is True
                    and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
                )
                hosts = {host.lower() for host in config.get("download_hosts", [])}
                if (parsed.scheme != "https" and not permitted_http) or not parsed.hostname or parsed.hostname.lower() not in hosts or parsed.username or parsed.password or parsed.fragment:
                    raise ValueError
                parsed.port
            except (ValueError, TypeError):
                raise APIError("result_url_rejected", uncertain=True) from None
            headers = self._headers() if self.result_requires_key(self.provider, locator) else {}
            data = self._request("GET", url, timeout, headers=headers, deadline=monotonic() + timeout).content
        if len(data) > self.max_response_bytes:
            raise APIError("response_too_large", uncertain=True)
        if not data:
            raise APIError("empty_result", uncertain=True)
        return [data]

    def discover(self, timeout: float = 10.0) -> list[str]:
        config = self.provider.get("discovery")
        if not config:
            return []
        payload = self._json_request("GET", config.get("path"), timeout, deadline=monotonic() + timeout)
        items = _path(payload, config.get("items_path", "data"))
        if not isinstance(items, list):
            raise APIError("invalid_discovery")
        identifiers = [_path(item, config.get("id_path", "id")) for item in items]
        return list(dict.fromkeys(value for value in identifiers if isinstance(value, str) and value))
