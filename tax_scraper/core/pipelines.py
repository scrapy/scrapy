"""
Item pipelines for processing and exporting scraped data.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from scrapy import Spider
from scrapy.exceptions import DropItem

from ..filters.tax_keywords import TaxKeywordFilter


class TaxContentPipeline:
    """
    Pipeline for validating and enriching tax content items.

    - Validates required fields
    - Filters out non-tax content (optional)
    - Enriches with additional classification
    """

    def __init__(self, min_content_length: int = 100, filter_non_tax: bool = False):
        self.min_content_length = min_content_length
        self.filter_non_tax = filter_non_tax
        self.tax_filter = TaxKeywordFilter()
        self.items_processed = 0
        self.items_dropped = 0

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            min_content_length=crawler.settings.getint("MIN_CONTENT_LENGTH", 100),
            filter_non_tax=crawler.settings.getbool("FILTER_NON_TAX", False),
        )

    def process_item(self, item, spider: Spider):
        # Validate required fields
        if not item.get("url"):
            self.items_dropped += 1
            raise DropItem("Missing URL")

        if not item.get("title"):
            self.items_dropped += 1
            raise DropItem(f"Missing title for {item['url']}")

        content = item.get("content", "")
        if len(content) < self.min_content_length:
            self.items_dropped += 1
            raise DropItem(
                f"Content too short ({len(content)} chars) for {item['url']}"
            )

        # Optionally filter non-tax content
        if self.filter_non_tax:
            if not self.tax_filter.is_tax_related(content):
                self.items_dropped += 1
                raise DropItem(f"Non-tax content: {item['url']}")

        self.items_processed += 1
        return item

    def close_spider(self, spider: Spider):
        spider.logger.info(
            f"TaxContentPipeline: processed {self.items_processed}, "
            f"dropped {self.items_dropped}"
        )


class JsonExportPipeline:
    """
    Pipeline for exporting items to JSON/JSONL files.

    Creates one file per spider run with all items.
    Also supports JSONL (one item per line) for streaming.
    """

    def __init__(self, output_dir: str = "./output", format: str = "jsonl"):
        self.output_dir = Path(output_dir)
        self.format = format  # 'json' or 'jsonl'
        self.file = None
        self.items = []
        self.filename = None

    @classmethod
    def from_crawler(cls, crawler):
        output_dir = crawler.settings.get("OUTPUT_DIR", "./output")
        output_format = crawler.settings.get("OUTPUT_FORMAT", "jsonl")
        return cls(output_dir=output_dir, format=output_format)

    def open_spider(self, spider: Spider):
        self.output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        extension = "jsonl" if self.format == "jsonl" else "json"
        self.filename = self.output_dir / f"{spider.name}_{timestamp}.{extension}"

        if self.format == "jsonl":
            self.file = open(self.filename, "w", encoding="utf-8")

        spider.logger.info(f"Output file: {self.filename}")

    def process_item(self, item, spider: Spider):
        item_dict = dict(item)

        if self.format == "jsonl":
            line = json.dumps(item_dict, ensure_ascii=False)
            self.file.write(line + "\n")
            self.file.flush()
        else:
            self.items.append(item_dict)

        return item

    def close_spider(self, spider: Spider):
        if self.format == "json":
            with open(self.filename, "w", encoding="utf-8") as f:
                json.dump(self.items, f, ensure_ascii=False, indent=2)

        if self.file:
            self.file.close()

        spider.logger.info(f"Exported {len(self.items) if self.items else 'items'} to {self.filename}")


class DuplicateFilterPipeline:
    """
    Pipeline for filtering duplicate items based on URL.
    """

    def __init__(self):
        self.seen_urls = set()

    def process_item(self, item, spider: Spider):
        url = item.get("url")
        if url in self.seen_urls:
            raise DropItem(f"Duplicate URL: {url}")

        self.seen_urls.add(url)
        return item
