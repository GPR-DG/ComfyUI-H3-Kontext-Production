from .nodes import (
    NODE_CLASS_MAPPINGS as API_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as API_NODE_DISPLAY_NAME_MAPPINGS,
    STORE,
)
from .h3_background_bridge import (
    NODE_CLASS_MAPPINGS as BRIDGE_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as BRIDGE_NODE_DISPLAY_NAME_MAPPINGS,
)

from .h3_kontext_bridge import (
    NODE_CLASS_MAPPINGS as KONTEXT_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as KONTEXT_NODE_DISPLAY_NAME_MAPPINGS,
)

if KONTEXT_NODE_CLASS_MAPPINGS.keys() & (API_NODE_CLASS_MAPPINGS.keys() | BRIDGE_NODE_CLASS_MAPPINGS.keys()):
    raise RuntimeError('Duplicate H3 Kontext node registration')
if API_NODE_CLASS_MAPPINGS.keys() & BRIDGE_NODE_CLASS_MAPPINGS.keys():
    raise RuntimeError('Duplicate H3 API/BackgroundBridge node registration')
NODE_CLASS_MAPPINGS = {**API_NODE_CLASS_MAPPINGS, **BRIDGE_NODE_CLASS_MAPPINGS, **KONTEXT_NODE_CLASS_MAPPINGS}
NODE_DISPLAY_NAME_MAPPINGS = {
    **API_NODE_DISPLAY_NAME_MAPPINGS, **BRIDGE_NODE_DISPLAY_NAME_MAPPINGS,
    **KONTEXT_NODE_DISPLAY_NAME_MAPPINGS,
}
WEB_DIRECTORY = './web'

try:
    from server import PromptServer
except ModuleNotFoundError as error:
    if error.name != 'server':
        raise
else:
    from .h3_adapter.routes import register_routes
    register_routes(PromptServer.instance.routes, STORE)

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', 'WEB_DIRECTORY']
