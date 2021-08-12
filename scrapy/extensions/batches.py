"""
Extensions for batch processing and support.
"""

import re
from scrapy.exceptions import NotConfigured
import time
from typing import Any, BinaryIO, Dict


class BatchHandler:
    """
    The default :ref:`batch handler <batches>`.

    To activate, define one of the following :ref:`feed options <feeds-options>`:

    .. setting:: FEED_EXPORT_BATCH_ITEM_COUNT

    - ``batch_item_count`` feed option or ``FEED_EXPORT_BATCH_ITEM_COUNT``
      setting (:class:`int`): the maximum number of items a batch can have.

      DEFAULT: ``0``

    .. setting:: FEED_EXPORT_BATCH_FILE_SIZE

    - ``batch_file_size`` feed options or ``FEED_EXPORT_BATCH_FILE_SIZE``
      setting (:class:`str`): deliver a batch file after it surpasses this file size.

      The file size format is ``<number><unit>``, where ``<unit>`` is a byte
      unit based on powers of 2 (KiB, MiB, GiB, TiB) or powers of 10 (kB, MB,
      GB, TB). Eg: 200MB, 100KiB.

      DEFAULT: ``0B``

    .. setting:: FEED_EXPORT_BATCH_DURATION

    - ``batch_duration`` feed options or ``FEED_EXPORT_BATCH_DURATION``
      setting (:class:`str`): deliver a batch file after at least this much time has passed.

      The duration format is ``hours:minutes:seconds``. Eg: 1:0:0 for 1 hour,
      0:30:0 for a 30 minute duration.

      Duration is only checked after an item is added to the batch file.

      DEFAULT: ``0:0:0``

    Each feed option overrides its counterpart setting.

    When using more than one type of limit, whichever limit exceeds first triggers a
    new batch file.
    """

    def __init__(self, feed_options: Dict[str, Any]) -> None:
        if not all(k in feed_options for k in ("batch_item_count", "batch_duration", "batch_file_size")):
            raise NotConfigured

        # get limits from feed_settings
        self.max_item_count: int = feed_options["batch_item_count"]
        self.max_seconds: float = self._in_seconds(feed_options["batch_duration"])
        self.max_file_size: int = self._in_bytes(feed_options["batch_file_size"])
        # initialize batch state attributes
        self.item_count: int = 0
        self.elapsed_seconds: float = 0
        self.file_size: int = 0
        # misc attributes
        self.file: BinaryIO
        self.start_time: float
        self.enabled: bool = any([self.max_item_count, self.max_seconds, self.max_file_size])

    def item_added(self) -> bool:
        if not self.enabled:
            return False

        self.item_count += 1
        self.elapsed_seconds = time.time() - self.start_time
        self.file_size = self.file.tell()

        if self.max_item_count and self.item_count >= self.max_item_count:
            return True
        if self.max_file_size and self.file_size >= self.max_file_size:
            return True
        if self.max_seconds and self.elapsed_seconds >= self.max_seconds:
            return True

        return False

    def new_batch(self, file: BinaryIO) -> None:
        self.file = file
        self.start_time = time.time()
        self.item_count = 0
        self.elapsed_seconds = 0
        self.file_size = 0

    def _in_seconds(self, duration: str) -> float:
        # Convert duration string in format: '<HOURS>:<MINUTES>:<SECONDS>' to seconds in float.
        h, m, s = map(float, duration.split(":"))
        duration_in_secs = h * 60 * 60 + m * 60 + s
        return duration_in_secs

    def _in_bytes(self, size: str) -> int:
        # Convert string size in format: '<SIZE><UNIT>' to bytes in integer.
        # https://stackoverflow.com/a/60708339/7116579
        units = {"B": 1, "KIB": 2**10, "MIB": 2**20, "GIB": 2**30, "TIB": 2**40,
                 "KB": 10**3, "MB": 10**6, "GB": 10**9, "TB": 10**12}
        match = re.search(r'(?i)^\s*(\d+)\s*((?:[kMGT]i?)?B)\s*$', size)
        if not match:
            raise ValueError(f'Invalid batch size: {size!r}')
        number, unit = match[1], match[2].upper()
        return int(float(number) * units[unit])
