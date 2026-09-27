# pragma: no file cover
import warnings

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils._ossignals import (
    SignalHandlerT,
    install_shutdown_handlers,
    signal_names,
)

warnings.warn(
    "The scrapy.utils.ossignal module is deprecated.",
    ScrapyDeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "SignalHandlerT",
    "install_shutdown_handlers",
    "signal_names",
]
