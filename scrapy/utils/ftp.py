# pragma: no file cover
import warnings

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils._ftp import ftp_makedirs_cwd, ftp_store_file

warnings.warn(
    "The scrapy.utils.ftp module is deprecated.",
    ScrapyDeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "ftp_makedirs_cwd",
    "ftp_store_file",
]
