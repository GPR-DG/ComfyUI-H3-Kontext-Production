"""ComfyUI administration endpoints, isolated from workflow serialization."""
import asyncio
import hmac
import json
import os
from urllib.parse import urlsplit
from aiohttp import web
from .config import ConfigError, ConfigConflict


def register_routes(routes, store):
    def authorize(request):
        if os.environ.get('H3_ADAPTER_DISABLE_MANAGEMENT') == '1':
            raise web.HTTPForbidden(text='Management disabled')
        origin = request.headers.get('Origin')
        if origin:
            try:
                parsed = urlsplit(origin)
                if parsed.netloc != request.host or parsed.scheme != request.scheme:
                    raise web.HTTPForbidden(text='Cross-origin administration denied')
            except ValueError:
                raise web.HTTPForbidden(text='Invalid origin') from None
        token = os.environ.get('H3_ADAPTER_MANAGEMENT_TOKEN', '')
        if token:
            try:
                supplied = request.headers.get('X-H3-Management-Token', '').encode('utf-8')
            except UnicodeEncodeError:
                raise web.HTTPUnauthorized(text='Administrator token required') from None
            if not hmac.compare_digest(supplied, token.encode('utf-8')):
                raise web.HTTPUnauthorized(text='Administrator token required')
        elif (request.remote not in ('127.0.0.1', '::1') or urlsplit('http://' + request.host).hostname not in ('localhost', '127.0.0.1', '::1') or request.headers.get('X-Forwarded-For') or request.headers.get('Forwarded')):
            raise web.HTTPForbidden(text='Remote management requires a server administrator token')

    async def body(request):
        authorize(request)
        if request.content_type != 'application/json' or request.content_length is None or request.content_length > 262144:
            raise web.HTTPBadRequest(text='Bounded JSON request required')
        try:
            value = await request.json()
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (ValueError, json.JSONDecodeError):
            raise web.HTTPBadRequest(text='Invalid JSON object') from None

    @routes.get('/h3-adapter/config')
    async def get_config(request):
        authorize(request)
        try:
            return web.json_response(store.public())
        except ConfigError as error:
            return web.json_response({'error': str(error)}, status=400)

    @routes.post('/h3-adapter/config')
    async def save_config(request):
        value = await body(request)
        try:
            revision = store.save(value.get('config'), value.get('expected_revision'))
            return web.json_response({'ok': True, 'revision': revision})
        except ConfigConflict:
            return web.json_response({'error': 'Configuration changed; reload before saving'}, status=409)
        except (ConfigError, TypeError, ValueError, KeyError):
            return web.json_response({'error': 'Invalid non-secret provider configuration'}, status=400)

    @routes.post('/h3-adapter/key')
    async def save_key(request):
        value = await body(request)
        try:
            store.save_key(value.get('provider_id'), value.get('key'), value.get('expected_revision'))
            return web.json_response({'ok': True, 'has_key': store.public()['keys'].get(value.get('provider_id'), False)})
        except ConfigConflict:
            return web.json_response({'error': 'Configuration changed; reload before saving a key'}, status=409)
        except (ConfigError, TypeError, ValueError, KeyError):
            return web.json_response({'error': 'Invalid provider or credential'}, status=400)

    @routes.post('/h3-adapter/models')
    async def models(request):
        value = await body(request)
        try:
            config = store.load()
            provider = next(p for p in config['providers'] if p['id'] == value.get('provider_id'))
            if not provider.get('discovery'):
                return web.json_response({'models': sorted({m['id'] for m in provider['models'].values()}),
                                          'source': 'manual', 'warning': 'No formal models API configured; manual IDs remain usable'})
            def discover():
                from .protocol import Protocol
                client = Protocol(provider, store.credential(provider, expected_revision=getattr(config, 'revision', None)))
                try:
                    return client.discover(timeout=min(30, provider.get('timeout_seconds', 30)))
                finally:
                    client.close()
            return web.json_response({'models': await asyncio.to_thread(discover), 'source': 'api'})
        except Exception:
            return web.json_response({'error': 'Models discovery failed; check documented endpoint/auth, or use a manual ID'}, status=400)
