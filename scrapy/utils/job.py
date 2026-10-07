# pragma: no file cover
import warnings

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.conf import _job_dir as job_dir

warnings.warn(
    "The scrapy.utils.job module is deprecated.",
    ScrapyDeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "job_dir",
]
