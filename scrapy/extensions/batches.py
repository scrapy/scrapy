"""
Extensions for batch processing and support.
"""

import re
import time
from typing import Any, BinaryIO, Dict


class BatchHandler:
    """
    The default batch handler for handling batch formation.

    To activate batching using the default batch handler, assign any criteria in the :ref:`feeds-options
    <feed-options>` of a feed with the desired limit. When using more than one criteria,
    whichever criteria is exceeded first will trigger the formation of the new batch.

    Accepted criteria:

    - ``batch_item_count``: Assign a limit on the number of items a batch can have.

        The limit must be an integer value.

    - ``batch_file_size``: Assign a soft limit to the size of a batch file.

        The limit must be a string in the format <``SIZE``><``STORAGE-UNIT``>, where ``STORAGE-UNIT``
        must be byte unit based on powers of 2(KiB, MiB, GiB, TiB) or powers of 10(kB, MB, GB, TB).
        Eg: 200MB, 100KiB.

    - ``batch_duration``: Assign a soft limit on the duration a batch stays active.

        Duration must be a string in the format ``hours:minutes:seconds``. Eg: 1:0:0 for 1 hour,
        0:30:0 for a 30 minute duration.

    Criteria can also be set in settings which will be assigned to all the feeds. But
    criteria assigned through feed-options will have higher priority.

    Equivalent settings criteria:

    .. setting:: FEED_EXPORT_BATCH_ITEM_COUNT

    - ``FEED_EXPORT_BATCH_ITEM_COUNT``: Equivalent to ``batch_item_count``.

        Default: ``0``

    .. setting:: FEED_EXPORT_BATCH_FILE_SIZE

    - ``FEED_EXPORT_BATCH_FILE_SIZE``: Equivalent to ``batch_file_size``.

        Default: ``0B``

    .. setting:: FEED_EXPORT_BATCH_DURATION

    - ``FEED_EXPORT_BATCH_DURATION``: Equivalent to ``batch_duration``.

        Default: ``0:0:0``
    """

    def __init__(self, feed_options: Dict[str, Any]) -> None:
        # get limits from feed_settings
        self.max_item_count: int = feed_options["batch_item_count"]
        self.max_seconds: float = self._in_seconds(feed_options["batch_duration"])
        self.max_file_size: int = self._in_bytes(feed_options["batch_file_size"])
        # initialize batch state attributes
        self.item_count: int = 0
        self.elapsed_seconds: float = 0
        self.file_size: int = 0
        self.batch_id: int = 0
        # misc attributes
        self.file: BinaryIO
        self.start_time: float
        self.enabled: bool = any([self.max_item_count, self.max_seconds, self.max_file_size])

    def item_added(self) -> None:
        """
        Update batch state attributes.
        """
        self.item_count += 1
        self.elapsed_seconds = time.time() - self.start_time
        self.file_size = self.file.tell()

    def should_trigger(self) -> bool:
        """
        Check if any batch state attribute has crossed its
        specified limit.
        :return: `True` if parameter value has crossed constraint, else `False`
        :rtype: bool
        """
        if not self.enabled:
            return False

        if self.max_item_count and self.item_count >= self.max_item_count:
            return True
        if self.max_file_size and self.file_size >= self.max_file_size:
            return True
        if self.max_seconds and self.elapsed_seconds >= self.max_seconds:
            return True

        return False

    def new_batch(self, file: BinaryIO) -> None:
        """
        Resets parameter values back to its initial value and increments
        self.batch_id.
        """
        self.file = file
        self.start_time = time.time()
        self.item_count = 0
        self.elapsed_seconds = 0
        self.file_size = 0
        self.batch_id += 1

    def _in_seconds(self, duration: str) -> float:
        """
        Convert duration string in format: '<HOURS>:<MINUTES>:<SECONDS>' to seconds in float.
        """
        h, m, s = map(float, duration.split(":"))
        duration_in_secs = h * 60 * 60 + m * 60 + s
        return duration_in_secs

    def _in_bytes(self, size: str) -> int:
        """
        Convert string size in format: '<SIZE><UNIT>' to bytes in integer.
        """
        # https://stackoverflow.com/a/60708339/7116579
        units = {"B": 1, "KIB": 2**10, "MIB": 2**20, "GIB": 2**30, "TIB": 2**40,
                 "KB": 10**3, "MB": 10**6, "GB": 10**9, "TB": 10**12}
        match = re.search(r'(?i)^\s*(\d+)\s*((?:[kMGT]i?)?B)\s*$', size)
        if not match:
            raise ValueError(f'Invalid batch size: {size!r}')
        number, unit = match[1], match[2].upper()
        return int(float(number) * units[unit])
