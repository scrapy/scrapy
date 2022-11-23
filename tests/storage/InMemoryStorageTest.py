import io
import os.path
import pickle
from unittest import TestCase

from scrapy.storage import in_memory
from scrapy.utils.project import data_path
from pathlib import Path


class InMemoryStorageTest(TestCase):
    def setUp(self):
        self.settings = dict()
        self.settings["COOKIES_PERSISTENCE_DIR"] = "cookies_test.txt"
        self.settings["COOKIES_PERSISTENCE"] = True
        self.storage = in_memory.InMemoryStorage(self.settings)
        self.path = data_path(self.settings["COOKIES_PERSISTENCE_DIR"])
        filename = Path(self.path)
        Path(".scrapy").mkdir(parents=True, exist_ok=True)
        filename.touch(exist_ok=True)

    def test_open_spider(self):
        self.storage.data = {"key1": "value1"}
        with io.open(self.path, "bw+") as f:
            pickle.dump(self.storage.data, f)

        self.storage.open_spider(None)
        self.assertEqual(self.storage.data["key1"], "value1")

    def test_close_spider(self):
        self.storage.data = {"key1": "value1"}
        with io.open(self.path, "bw+") as f:
            pickle.dump(self.storage.data, f)

        self.storage.data["key2"] = "value2"
        self.storage.close_spider(None)

        with io.open(self.storage.cookies_dir, "br") as f:
            self.data = pickle.load(f)

        self.assertEqual(self.data["key1"], "value1")
        self.assertEqual(self.data["key2"], "value2")
