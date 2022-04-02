import io
import logging
import os
import pickle
from collections import UserDict
from typing import Dict

from scrapy.http.cookies import CookieJar
from scrapy.spiders import Spider
from scrapy.storage import BaseStorage
from scrapy.utils.project import data_path

logger = logging.getLogger(__name__)


class InMemoryStorage(UserDict, BaseStorage):
    def __init__(self, settings):
        super(InMemoryStorage, self).__init__()
        self.settings = settings
        self.cookies_dir = data_path(settings["COOKIES_PERSISTENCE_DIR"])

    def open_spider(self, spider: Spider):
        if not self.settings["COOKIES_PERSISTENCE"]:
            return
        if not os.path.exists(self.cookies_dir):
            return
        with io.open(self.cookies_dir, "br") as f:
            self.data: Dict = pickle.load(f)

    def close_spider(self, spider):
        if self.settings["COOKIES_PERSISTENCE"]:
            with io.open(self.cookies_dir, "bw") as f:
                pickle.dump(self.data, f)

    def __missing__(self, key) -> CookieJar:
        self.data.update({key: CookieJar()})
        return self.data[key]
