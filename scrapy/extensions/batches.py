"""
Extensions for batch processing and support.
"""

import re
import time
from typing import Any, BinaryIO, Dict


class BatchHandler:
    """
    A batch handler which will store information for current batches
    and provides suitable methods to check and update batch info.
    """

    def __init__(self, feed_options: Dict[str, Any]) -> None:
        self.feed_options: Dict[str, Any] = feed_options
        # get limits from feed_settings
        self.max_item_count: int = self.feed_options["batch_item_count"]
        self.max_time_duration: str = self._in_seconds(self.feed_options["batch_time_duration"])
        self.max_file_size: str = self._in_bytes(self.feed_options["batch_file_size"])
        # initialize batch state attributes
        self.item_count: int = 0
        self.elapsed_time: int = 0
        self.file_size: int = 0
        self.batch_id: int = 0
        # misc attributes
        self.file: BinaryIO
        self.start_time: int
        self.updated_once: bool = False
        self.enabled: bool = True
        if not any([self.max_item_count, self.max_time_duration, self.max_file_size]):
            self.enabled = False

    def update(self) -> None:
        """
        Update batch state attributes.
        """
        self.item_count += 1
        self.elapsed_time = self._calculate_elapsed_time()
        self.file_size = self._calculate_batch_size()

        if not self.updated_once:
            self.updated_once = True

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
        if self.max_time_duration and self.elapsed_time >= self.max_time_duration:
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
        self.elapsed_time = 0
        self.file_size = 0
        self.updated_once = False
        self.batch_id += 1

    def get_batch_state(self) -> Dict[str, int]:
        """
        Get current batch state.
        :return: A dictionary containing batch state parameters and its current value.
        :rtype: dict
        """
        state = {
            'itemcount': self.item_count,
            'duration(seconds)': self.elapsed_time,
            'file size(bytes)': self.file_size,
        }
        return state

    def _in_seconds(self, duration: str) -> int:
        """
        Convert duration string in format: '<HOURS>:<MINUTES>:<SECONDS>' to seconds in integer.
        """
        h, m, s = map(int, duration.split(":"))
        duration_in_secs = h * 60 * 60 + m * 60 + s
        return duration_in_secs

    def _in_bytes(self, size: str) -> int:
        """
        Convert string size in format: '<SIZE><UNIT>' to bytes in integer.
        """
        # https://stackoverflow.com/a/60708339/7116579
        units = {"B": 1, "KB": 2**10, "MB": 2**20, "GB": 2**30, "TB": 2**40}
        size = size.upper()
        if not re.match(r' ', size):
            size = re.sub(r'([KMGT]?B)', r' \1', size)
        number, unit = [string.strip() for string in size.split()]
        return int(float(number) * units[unit])

    def _calculate_elapsed_time(self) -> int:
        return time.time() - self.start_time

    def _calculate_batch_size(self) -> int:
        return self.file.tell()
