# pragma: no file cover
import warnings

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils._signal import (
    disconnect_all,
    send_catch_log,
    send_catch_log_async,
    send_catch_log_deferred,
)

warnings.warn(
    "The scrapy.utils.signal module is deprecated.",
    ScrapyDeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "disconnect_all",
    "send_catch_log",
    "send_catch_log_async",
    "send_catch_log_deferred",
]
