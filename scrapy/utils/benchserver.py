import warnings

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils._benchserver import main

warnings.warn(
    "scrapy.utils.benchserver is deprecated.",
    category=ScrapyDeprecationWarning,
    stacklevel=2,
)

if __name__ == "__main__":
    main()