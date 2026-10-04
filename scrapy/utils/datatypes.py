# pragma: no file cover
import warnings

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils._datatypes import (
    CaseInsensitiveDict,
    LocalCache,
    LocalWeakReferencedCache,
    SequenceExclude,
)

warnings.warn(
    "The scrapy.utils.datatypes module is deprecated.",
    ScrapyDeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "CaseInsensitiveDict",
    "LocalCache",
    "LocalWeakReferencedCache",
    "SequenceExclude",
]
