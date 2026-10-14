from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from scrapy.pqueues import _path_safe
from tests.utils.cmdline import proc

if TYPE_CHECKING:
    from pathlib import Path


# Dies without any cleanup once kill_at requests have reached the scheduler.
SPIDER = """
import os

from scrapy import Request, Spider, signals


class KillSpider(Spider):
    name = "kill"
    custom_settings = {
        "SCHEDULER_DISK_QUEUE": "scrapy.squeues.PickleFifoSQLiteQueue",
        "SCHEDULER_START_DISK_QUEUE": "scrapy.squeues.PickleFifoSQLiteQueue",
        "CONCURRENT_REQUESTS": 1,
        "JOBDIR_SYNC_EVERY": 1,
    }

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        spider.scheduled = 0
        crawler.signals.connect(spider.request_scheduled, signals.request_scheduled)
        return spider

    def request_scheduled(self, request, spider):
        self.scheduled += 1
        if self.scheduled == int(getattr(self, "kill_at", 0)):
            os._exit(1)

    async def start(self):
        if hasattr(self, "resume"):
            return
        for i in range(20):
            yield Request(f"data:,{i}", priority=i % 3)

    def parse(self, response):
        self.logger.info(f"Parsed {response.url}")
"""


def run(tmp_path: Path, *args: str) -> str:
    spider = tmp_path / "spider.py"
    spider.write_text(SPIDER, encoding="utf-8")
    jobdir = tmp_path / "job"
    _, _, log = proc(
        "runspider", str(spider), "-s", f"JOBDIR={jobdir}", *args, cwd=tmp_path
    )
    return log


def _active_json(tmp_path: Path) -> Any:
    path = tmp_path / "job" / "requests.queue" / "active.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_resume_after_kill(tmp_path: Path) -> None:
    # The delay keeps all but the first request or two in the queue when the
    # spider dies, while start requests keep being scheduled eagerly.
    run(tmp_path, "-a", "kill_at=10", "-s", "DOWNLOAD_DELAY=5")
    [(slot, priorities)] = _active_json(tmp_path).items()
    slot_dir = tmp_path / "job" / "requests.queue" / _path_safe(slot)
    assert set(priorities) == {
        int(path.name.rstrip("s")) for path in slot_dir.iterdir()
    }

    log = run(tmp_path, "-a", "resume=1")
    match = re.search(r"Resuming crawl \((\d+) requests scheduled\)", log)
    assert match, log
    pending = int(match.group(1))
    assert pending > 0
    assert log.count("Parsed data:,") == pending
    assert "Spider closed (finished)" in log
    assert _active_json(tmp_path) == {}
