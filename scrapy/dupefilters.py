import logging
import os
import re

from scrapy.utils.job import job_dir
from scrapy.utils.misc import load_object
from scrapy.utils.request import default_request_key_builder, referer_str


class BaseDupeFilter(object):

    @classmethod
    def from_settings(cls, settings):
        return cls()

    def request_seen(self, request):
        return False

    def open(self):  # can return deferred
        pass

    def close(self, reason):  # can return a deferred
        pass

    def log(self, request, spider):  # log that a request has been filtered
        pass


def _escape_line_breaks(data):
    """Returns `data` with escaped line breaks"""
    return data.replace(b'\\', b'\\\\').replace(b'\n', b'\\n')


def _unescape_line_breaks(data):
    """Performs the reverse process of
    :func:`scrapy.dupefilters._escape_line_breaks`."""
    value = re.sub(b'(^|[^\\\\])((?:\\\\\\\\)*?)\\\\n', b'\\1\\2\n', data)
    return value.replace(b'\\\\', b'\\')


class RFPDupeFilter(BaseDupeFilter):
    """Request Fingerprint duplicates filter"""

    def __init__(self, path=None, debug=False,
                 key_builder=default_request_key_builder):
        self.file = None
        self.build_key = key_builder
        self.keys = set()
        self.logdupes = True
        self.debug = debug
        self.logger = logging.getLogger(__name__)
        if path:
            self.file = open(os.path.join(path, 'requests.seen'), 'ab+')
            self.file.seek(0)
            for escaped_key in self.file:
                try:
                    key = _unescape_line_breaks(escaped_key[:-1])
                except ValueError:
                    pass
                else:
                    self.keys.add(key)

    @classmethod
    def from_settings(cls, settings):
        debug = settings.getbool('DUPEFILTER_DEBUG')
        key_builder = load_object(settings['REQUEST_KEY_BUILDER'])
        return cls(job_dir(settings), debug, key_builder)

    def request_seen(self, request):
        key = self.build_key(request)
        if key in self.keys:
            return True
        self.keys.add(key)
        if self.file:
            self.file.write(_escape_line_breaks(key) + b'\n')

    def close(self, reason):
        if self.file:
            self.file.close()

    def log(self, request, spider):
        if self.debug:
            msg = "Filtered duplicate request: %(request)s (referer: %(referer)s)"
            args = {'request': request, 'referer': referer_str(request) }
            self.logger.debug(msg, args, extra={'spider': spider})
        elif self.logdupes:
            msg = ("Filtered duplicate request: %(request)s"
                   " - no more duplicates will be shown"
                   " (see DUPEFILTER_DEBUG to show all duplicates)")
            self.logger.debug(msg, {'request': request}, extra={'spider': spider})
            self.logdupes = False

        spider.crawler.stats.inc_value('dupefilter/filtered', spider=spider)
