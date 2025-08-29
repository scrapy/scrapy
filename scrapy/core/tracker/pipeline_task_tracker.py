"""
PipelineTaskTracker: Internal utility for tracking asynchronous item processing tasks.

Used by Scraper to ensure all item pipeline tasks complete before spider shutdown.
"""

import datetime
import logging

logger = logging.getLogger(__name__)


class PipelineTaskTracker:
    def __init__(self):
        self.records = []

    def track(self, item, request, spider):
        record = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "spider": getattr(spider, "name", None),
            "url": getattr(request, "url", None),
            "item_type": type(item).__name__,
            "item_preview": str(item)[:100],  # Truncated for readability
        }
        self.records.append(record)
        logger.debug(f"[PipelineTracker] Tracked item: {record}")
