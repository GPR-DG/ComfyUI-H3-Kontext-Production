"""Deployment-only aggregation; upstream implementations remain byte-for-byte intact."""
from .h3_core import NODE_CLASS_MAPPINGS as CORE_CLASSES
from .h3_core import NODE_DISPLAY_NAME_MAPPINGS as CORE_NAMES
from .h3_adapter_bundle import NODE_CLASS_MAPPINGS as ADAPTER_CLASSES
from .h3_adapter_bundle import NODE_DISPLAY_NAME_MAPPINGS as ADAPTER_NAMES

if CORE_CLASSES.keys() & ADAPTER_CLASSES.keys():
    raise RuntimeError("Duplicate upstream H3 node registrations")

NODE_CLASS_MAPPINGS = {**CORE_CLASSES, **ADAPTER_CLASSES}
NODE_DISPLAY_NAME_MAPPINGS = {**CORE_NAMES, **ADAPTER_NAMES}

# Compatibility registration keys ONLY. No new classes, wrappers or algorithms.
REGISTRATION_ALIASES = {
    "H3CBackgroundFinish": "H3CBackgroundAttachClean",
    "H3StageGuard": "H3KStageGuard",
    "H3StagePreview": "H3KStagePreview",
}
for alias, canonical in REGISTRATION_ALIASES.items():
    NODE_CLASS_MAPPINGS[alias] = NODE_CLASS_MAPPINGS[canonical]
    NODE_DISPLAY_NAME_MAPPINGS[alias] = NODE_DISPLAY_NAME_MAPPINGS[canonical]

REQUIRED_NODES = (
    "H3CBackgroundTaskStart", "H3CBestBackgroundFrame", "H3CBackgroundResolve",
    "H3CBackgroundWashClaim", "H3CBackgroundFinish", "H3CBackgroundTaskCleanup",
    "H3KBackgroundResolve", "H3KBackgroundWashClaim", "H3KBackgroundFinish",
    "H3KBackgroundSource", "H3StageGuard", "H3KRecipe", "H3KPromptCapture", "H3StagePreview",
)
if set(REQUIRED_NODES) - NODE_CLASS_MAPPINGS.keys():
    raise RuntimeError("Required production H3 nodes failed to register")

WEB_DIRECTORY = "./h3_adapter_bundle/web"
__version__ = "0.1.0"
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
