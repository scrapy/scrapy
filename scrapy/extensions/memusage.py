"""
MemoryUsage extension

See documentation in docs/topics/extensions.rst
"""
import sys
import socket
import logging
from pprint import pformat
from importlib import import_module

from twisted.internet import task

from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.mail import MailSender
from scrapy.utils.engine import get_engine_status

logger = logging.getLogger(__name__)


class MemoryUsage(object):

    def __init__(self, crawler):
        if not crawler.settings.getbool('MEMUSAGE_ENABLED'):
            raise NotConfigured
        try:
            # stdlib's resource module is only available on unix platforms.
            self.resource = import_module('resource')
        except ImportError:
            raise NotConfigured

        self.crawler = crawler
        self.warned = False
        self.notify_mails = crawler.settings.getlist('MEMUSAGE_NOTIFY_MAIL')
        self.limit = crawler.settings.getint('MEMUSAGE_LIMIT_MB')*1024*1024
        self.warning = crawler.settings.getint('MEMUSAGE_WARNING_MB')*1024*1024
        self.report = crawler.settings.getbool('MEMUSAGE_REPORT')
        self.check_interval = crawler.settings.getfloat('MEMUSAGE_CHECK_INTERVAL_SECONDS')
        self.mail = MailSender.from_settings(crawler.settings)
        crawler.signals.connect(self.engine_started, signal=signals.engine_started)
        crawler.signals.connect(self.engine_stopped, signal=signals.engine_stopped)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def get_virtual_size(self):
        size = self.resource.getrusage(self.resource.RUSAGE_SELF).ru_maxrss
        if sys.platform != 'darwin':
            # on Mac OS X ru_maxrss is in bytes, on Linux it is in KB
            size *= 1024
        return size

    def engine_started(self):
        self.crawler.stats.set_value('memusage/startup', self.get_virtual_size())
        self.tasks = []
        tsk = task.LoopingCall(self.update)
        self.tasks.append(tsk)
        tsk.start(self.check_interval, now=True)
        if self.limit:
            tsk = task.LoopingCall(self._check_limit)
            self.tasks.append(tsk)
            tsk.start(self.check_interval, now=True)
        if self.warning:
            tsk = task.LoopingCall(self._check_warning)
            self.tasks.append(tsk)
            tsk.start(self.check_interval, now=True)

    def engine_stopped(self):
        for tsk in self.tasks:
            if tsk.running:
                tsk.stop()

    def update(self):
        self.crawler.stats.max_value('memusage/max', self.get_virtual_size())

    def _check_limit(self):
        if self.get_virtual_size() > self.limit:
            self.crawler.stats.set_value('memusage/limit_reached', 1)
            mem = self.limit/1024/1024
            logger.error("Memory usage exceeded %(memusage)dM. Shutting down Scrapy...",
                         {'memusage': mem}, extra={'crawler': self.crawler})
            if self.notify_mails:
                subj = "%s terminated: memory usage exceeded %dM at %s" % \
                        (self.crawler.settings['BOT_NAME'], mem, socket.gethostname())
                self._send_report(self.notify_mails, subj)
                self.crawler.stats.set_value('memusage/limit_notified', 1)

            open_spiders = self.crawler.engine.open_spiders
            if open_spiders:
                for spider in open_spiders:
                    self.crawler.engine.close_spider(spider, 'memusage_exceeded')
            else:
                self.crawler.stop()

    def _check_warning(self):
        if self.warned: # warn only once
            return
        if self.get_virtual_size() > self.warning:
            self.crawler.stats.set_value('memusage/warning_reached', 1)
            mem = self.warning/1024/1024
            logger.warning("Memory usage reached %(memusage)dM",
                           {'memusage': mem}, extra={'crawler': self.crawler})
            if self.notify_mails:
                subj = "%s warning: memory usage reached %dM at %s" % \
                        (self.crawler.settings['BOT_NAME'], mem, socket.gethostname())
                self._send_report(self.notify_mails, subj)
                self.crawler.stats.set_value('memusage/warning_notified', 1)
            self.warned = True

    def _send_report(self, rcpts, subject):
        """send notification mail with some additional useful info"""
        stats = self.crawler.stats
        s = "Memory usage at engine startup : %dM\r\n" % (stats.get_value('memusage/startup')/1024/1024)
        s += "Maximum memory usage           : %dM\r\n" % (stats.get_value('memusage/max')/1024/1024)
        s += "Current memory usage           : %dM\r\n" % (self.get_virtual_size()/1024/1024)

        s += "ENGINE STATUS ------------------------------------------------------- \r\n"
        s += "\r\n"
        s += pformat(get_engine_status(self.crawler.engine))
        s += "\r\n"
        self.mail.send(rcpts, subject, s)
