# pragma: no file cover
import warnings

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils._shell import (
    DEFAULT_PYTHON_SHELLS,
    EmbedFuncT,
    KnownShellsT,
    get_shell_embed_func,
    start_python_console,
)

warnings.warn(
    "The scrapy.utils.console module is deprecated.",
    ScrapyDeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "DEFAULT_PYTHON_SHELLS",
    "EmbedFuncT",
    "KnownShellsT",
    "get_shell_embed_func",
    "start_python_console",
]
