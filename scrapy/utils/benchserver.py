# pragma: no file cover
import warnings

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils._benchserver import Root, main

warnings.warn(
    "The scrapy.utils.benchserver module is deprecated.",
    ScrapyDeprecationWarning,
    stacklevel=2,
)


__all__ = [
    "Root",
]


if __name__ == "__main__":
    main()
