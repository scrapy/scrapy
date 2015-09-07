import os
import logging

from twisted.python.failure import Failure

from scrapy.utils.request import referer_str

SCRAPEDMSG = u"Scraped from %(src)s" + os.linesep + "%(item)s"
DROPPEDMSG = u"Dropped: %(exception)s" + os.linesep + "%(item)s"
CRAWLEDMSG = u"Crawled (%(status)s) %(request)s (referer: %(referer)s)%(flags)s"


class LogFormatter(object):
    """Class for generating log messages for different actions.

    All methods must return a dictionary listing the parameters `level`, `msg`
    and `args` which are going to be used for constructing the log message when
    calling logging.log.

    Dictionary keys for the method outputs:
        * `level` should be the log level for that action, you can use those
        from the python logging library: logging.DEBUG, logging.INFO,
        logging.WARNING, logging.ERROR and logging.CRITICAL.

        * `msg` should be a string that can contain different formatting
        placeholders. This string, formatted with the provided `args`, is going
        to be the log message for that action.

        * `args` should be a tuple or dict with the formatting placeholders for
        `msg`.  The final log message is computed as output['msg'] %
        output['args'].
    """

    def crawled(self, request, response, spider):
        flags = ' %s' % str(response.flags) if response.flags else ''
        return {
            'level': logging.DEBUG,
            'msg': CRAWLEDMSG,
            'args': {
                'status': response.status,
                'request': request,
                'referer': referer_str(request),
                'flags': flags,
            }
        }

    def scraped(self, item, response, spider):
        if isinstance(response, Failure):
            src = response.getErrorMessage()
        else:
            src = response
        return {
            'level': logging.DEBUG,
            'msg': SCRAPEDMSG,
            'args': {
                'src': src,
                'item': item,
            }
        }

    def dropped(self, item, exception, response, spider):
        return {
            'level': logging.WARNING,
            'msg': DROPPEDMSG,
            'args': {
                'exception': exception,
                'item': item,
            }
        }

    @classmethod
    def from_crawler(cls, crawler):
        return cls()
