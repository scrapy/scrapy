# pragma: no file cover
import warnings

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils._template import (
    CAMELCASE_INVALID_CHARS,
    render_templatefile,
    string_camelcase,
)

warnings.warn(
    "The scrapy.utils.template module is deprecated.",
    ScrapyDeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "CAMELCASE_INVALID_CHARS",
    "render_templatefile",
    "string_camelcase",
]
