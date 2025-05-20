Scrapy Priority Scheduler
A Scrapy plugin that implements a custom scheduler to prioritize "branch" requests (which yield additional requests) over "leaf" requests (which do not) to optimize memory usage and maintain concurrency.
Installation
pip install scrapy-priority-scheduler

Usage

Add the plugin to your Scrapy project's settings.py:

SCHEDULER = "scrapy_priority_scheduler.scheduler.PriorityScheduler"
PRIORITY_SCHEDULER_MULTIPLIER = 2.0  # Adjust the multiplier as needed


Mark requests as "branch" or "leaf" in your spider using Request.meta:

import scrapy

class MySpider(scrapy.Spider):
    name = "myspider"
    start_urls = ["https://quotes.toscrape.com"]

    def parse(self, response):
        # Branch request: yields additional requests
        for href in response.css("div.quote a::attr(href)").getall():
            yield scrapy.Request(
                response.urljoin(href),
                callback=self.parse_quote,
                meta={"priority_type": "branch"}
            )
        # Branch request: next page
        next_page = response.css("li.next a::attr(href)").get()
        if next_page:
            yield scrapy.Request(
                response.urljoin(next_page),
                callback=self.parse,
                meta={"priority_type": "branch"}
            )

    def parse_quote(self, response):
        # Leaf request: extracts items, no further requests
        yield {
            "quote": response.css("span.text::text").get(),
            "author": response.css("span small::text").get()
        }
        # Explicitly mark as leaf
        yield scrapy.Request(
            response.url,
            callback=self.parse_quote,
            meta={"priority_type": "leaf"},
            dont_filter=True  # For demonstration
        )

Settings

SCHEDULER: Set to "scrapy_priority_scheduler.scheduler.PriorityScheduler".
PRIORITY_SCHEDULER_MULTIPLIER: Multiplier for branch request threshold (default: 2.0).

How It Works

The scheduler maintains separate queues for branch and leaf requests per domain.
Branch requests are prioritized when the number of active branch requests is below CONCURRENT_REQUESTS_PER_DOMAIN * PRIORITY_SCHEDULER_MULTIPLIER.
Leaf requests are prioritized otherwise to maintain concurrency.
Requests without a priority_type in Request.meta trigger a warning and are treated as leaf requests.

Requirements

Scrapy >= 2.13.0
Python >= 3.9

License
BSD-3-Clause
