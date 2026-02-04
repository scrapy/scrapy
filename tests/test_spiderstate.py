from datetime import datetime, timezone

import pytest

from scrapy.exceptions import NotConfigured
from scrapy.extensions.spiderstate import SpiderState
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler


def test_store_load(tmp_path):
    jobdir = str(tmp_path)

    spider = Spider(name="default")
    dt = datetime.now(tz=timezone.utc)

    ss = SpiderState(jobdir)
    ss.spider_opened(spider)
    spider.state["one"] = 1
    spider.state["dt"] = dt
    ss.spider_closed(spider)

    spider2 = Spider(name="default")
    ss2 = SpiderState(jobdir)
    ss2.spider_opened(spider2)
    assert spider.state == {"one": 1, "dt": dt}
    ss2.spider_closed(spider2)


def test_state_attribute():
    # state attribute must be present if jobdir is not set, to provide a
    # consistent interface
    spider = Spider(name="default")
    ss = SpiderState()
    ss.spider_opened(spider)
    assert spider.state == {}
    ss.spider_closed(spider)


def test_not_configured():
    crawler = get_crawler(Spider)
    with pytest.raises(NotConfigured):
        SpiderState.from_crawler(crawler)
