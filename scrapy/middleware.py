import logging
import pprint
from collections import defaultdict, deque
from typing import Callable, Deque, Dict

from twisted.internet.defer import Deferred

from scrapy import Spider
from scrapy.exceptions import NotConfigured
from scrapy.settings import Settings
from scrapy.utils.misc import create_instance, load_object
from scrapy.utils.defer import process_parallel, process_chain, process_chain_both

logger = logging.getLogger(__name__)


class MiddlewareManager:
    """Base class for implementing middleware managers"""

    component_name = 'foo middleware'

    def __init__(self, *middlewares):
        self.middlewares = middlewares
        self.methods: Dict[str, Deque[Callable]] = defaultdict(deque)
        for mw in middlewares:
            self._add_middleware(mw)

    @classmethod
    def _get_mwlist_from_settings(cls, settings: Settings) -> list:
        raise NotImplementedError

    @classmethod
    def from_settings(cls, settings: Settings, crawler=None):
        mwlist = cls._get_mwlist_from_settings(settings)
        middlewares = []
        enabled = []
        for clspath in mwlist:
            try:
                mwcls = load_object(clspath)
                mw = create_instance(mwcls, settings, crawler)
                middlewares.append(mw)
                enabled.append(clspath)
            except NotConfigured as e:
                if e.args:
                    clsname = clspath.split('.')[-1]
                    logger.warning("Disabled %(clsname)s: %(eargs)s",
                                   {'clsname': clsname, 'eargs': e.args[0]},
                                   extra={'crawler': crawler})

        logger.info("Enabled %(componentname)ss:\n%(enabledlist)s",
                    {'componentname': cls.component_name,
                     'enabledlist': pprint.pformat(enabled)},
                    extra={'crawler': crawler})
        return cls(*middlewares)

    @classmethod
    def from_crawler(cls, crawler):
        return cls.from_settings(crawler.settings, crawler)

    def _add_middleware(self, mw) -> None:
        if hasattr(mw, 'open_spider'):
            self.methods['open_spider'].append(mw.open_spider)
        if hasattr(mw, 'close_spider'):
            self.methods['close_spider'].appendleft(mw.close_spider)

    def _process_parallel(self, methodname: str, obj, *args) -> Deferred:
        return process_parallel(self.methods[methodname], obj, *args)

    def _process_chain(self, methodname: str, obj, *args) -> Deferred:
        return process_chain(self.methods[methodname], obj, *args)

    def _process_chain_both(self, cb_methodname: str, eb_methodname: str, obj, *args) -> Deferred:
        return process_chain_both(self.methods[cb_methodname],
                                  self.methods[eb_methodname], obj, *args)

    def open_spider(self, spider: Spider) -> Deferred:
        return self._process_parallel('open_spider', spider)

    def close_spider(self, spider: Spider) -> Deferred:
        return self._process_parallel('close_spider', spider)
