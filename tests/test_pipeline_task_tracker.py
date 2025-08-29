import unittest
from datetime import datetime
from scrapy.core.tracker.pipeline_task_tracker import PipelineTaskTracker


class DummyRequest:
    def __init__(self, url):
        self.url = url


class DummySpider:
    name = "test_spider"


class DummyItem(dict):
    pass


class TestPipelineTaskTracker(unittest.TestCase):
    def setUp(self):
        self.tracker = PipelineTaskTracker()
        self.item = DummyItem({"title": "Test"})
        self.request = DummyRequest("http://example.com")
        self.spider = DummySpider()

    def test_track_records_metadata(self):
        self.tracker.track(self.item, self.request, self.spider)
        record = self.tracker.records[0]

        self.assertEqual(record["spider"], "test_spider")
        self.assertEqual(record["url"], "http://example.com")
        self.assertEqual(record["item_type"], "DummyItem")
        self.assertIn("timestamp", record)

        # Validate timestamp format (ISO 8601)
        try:
            parsed = datetime.fromisoformat(record["timestamp"])
        except ValueError:
            self.fail("Timestamp is not in valid ISO 8601 format")

    def test_track_with_none_request(self):
        self.tracker.track(self.item, None, self.spider)
        record = self.tracker.records[0]
        self.assertIsNone(record["url"])

    def test_track_with_none_spider(self):
        self.tracker.track(self.item, self.request, None)
        record = self.tracker.records[0]
        self.assertIsNone(record["spider"])

    def test_multiple_tracks_are_isolated(self):
        tracker2 = PipelineTaskTracker()
        self.tracker.track(self.item, self.request, self.spider)
        tracker2.track(self.item, self.request, self.spider)

        self.assertEqual(len(self.tracker.records), 1)
        self.assertEqual(len(tracker2.records), 1)
        self.assertNotEqual(id(self.tracker.records), id(tracker2.records))


if __name__ == "__main__":
    unittest.main()
