try:
    from ._version import version as __version__
except ImportError:
    # broken installation, we don't even try
    # unknown only works because we do poor mans version compare
    __version__ = "unknown"

__all__ = [
    "__version__",
    "PluginManager",
    "PluginValidationError",
    "HookCaller",
    "HookCallError",
    "HookspecOpts",
    "HookimplOpts",
    "HookImpl",
    "HookRelay",
    "HookspecMarker",
    "HookimplMarker",
    "Result",
]

from ._manager import PluginManager, PluginValidationError
from ._result import HookCallError, Result
from ._hooks import (
    HookspecMarker,
    HookimplMarker,
    HookCaller,
    HookRelay,
    HookspecOpts,
    HookimplOpts,
    HookImpl,
)
