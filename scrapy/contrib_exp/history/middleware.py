import hashlib
from datetime import datetime

from scrapy.xlib.pydispatch import dispatcher

from scrapy.utils.misc import load_object
from scrapy.core import signals
from scrapy import log
from scrapy.core.exceptions import NotConfigured, IgnoreRequest
from scrapy.conf import settings

class HistoryMiddleware(object):
    # How often we should re-check links we know about
    MIN_CHECK_DAYS = 4
    # How often we should process pages that have not changed (need to include depth)
    MIN_PROCESS_UNCHANGED_DAYS = 12

    def __init__(self):
        historycls = load_object(settings['MEMORYSTORE'])
        if not historycls:
            raise NotConfigured
        self.historydata = historycls()
        dispatcher.connect(self.open_domain, signal=signals.domain_open)
        dispatcher.connect(self.close_domain, signal=signals.domain_closed)

    def process_request(self, request, spider):
        key = urlkey(request.url)
        status = self.historydata.status(domain, key)
        if status:
            _url, version, last_checked = status
            d = datetime.now() - last_checked
            if d.days < self.MIN_CHECK_DAYS:
                raise IgnoreRequest("Not scraping %s (scraped %s ago)" % (request.url, d))
            request.meta['history_response_version'] = version

    def process_response(self, request, response, spider):
        version = request.meta.get('history_response_version')
        if version == self.get_version(response):
            del request.content['history_response_version']
            hist = self.historydata.version_info(domain, version)
            if hist:
                versionkey, created = hist
                # if versionkey != urlkey(url) this means
                # the same content is available on a different url
                delta = datetime.now() - created
                if delta.days < self.MIN_PROCESS_UNCHANGED_DAYS:
                    message = "skipping %s: unchanged for %s" % (response.url, delta)
                    raise IgnoreRequest(message)
        self.record_visit(domain, request, response)
        return response

    def process_exception(self, request, exception, spider):
        self.record_visit(spider.domain_name, request, None)

    def open_domain(self, domain):
        self.historydata.open(domain)

    def close_domain(self, domain):
        self.historydata.close_site(domain)

    def record_visit(self, domain, request, response):
        """record the fact that the url has been visited"""
        url = request.url
        post_version = hash(request.body)
        key = urlkey(url)
        if response:
            redirect_url = response.url
            parentkey = urlkey(response.request.headers.get('referer')) if response.request else None
            version = self.get_version(response)
        else:
            redirect_url, parentkey, version = url, None, None
        self.historydata.store(domain, key, url, parentkey, version, post_version)

    def get_version(self, response):
        key = hashlib.sha1(response.body).hexdigest()

def urlkey(url):
    """Generate a 'key' for a given url

    >>> urlkey("http://www.example.com/")
    '89e6a0649e06d83370cdf2cbfb05f363934a8d0c'
    >>> urlkey("http://www.example.com/") == urlkey("http://www.example.com/?")
    True
    """
    from scrapy.utils.c14n import canonicalize
    return hash(canonicalize(url))


def hash(value):
    return hashlib.sha1(value).hexdigest() if value else None
