from xdist.plugin import (
    is_xdist_worker,
    is_xdist_master,
    get_xdist_worker_id,
    is_xdist_controller,
)
from xdist._version import version as __version__

__all__ = [
    "__version__",
    "is_xdist_worker",
    "is_xdist_master",
    "is_xdist_controller",
    "get_xdist_worker_id",
]
