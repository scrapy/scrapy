import re
import urllib
import simplejson
from sha import sha
from twisted.internet import defer

from scrapy.core.engine import scrapyengine
from scrapy.spider import spiders
from scrapy.http import Request
from scrapy.item import ScrapedItem
from scrapy.core.exceptions import NotConfigured
from scrapy.conf import settings
from scrapy.utils.misc import memoize
from lrucache import LRUCache

from .site import WebSite, WebResource
from .http import HttpResponse
from .json import JsonResponse

JSONCALLBACK_RE = '^[a-zA-Z][a-zA-Z_.-]*$'
CACHESIZE = settings.get('WS_CACHESIZE', 20)


def _urlhash(request):
    h = sha()
    for a in sorted(request.ARGS):
        h.update(request.ARGS[a])
    return h.hexdigest()


@memoize(cache=LRUCache(CACHESIZE), hash=_urlhash)
def url_to_guid(httprequest):
    url = httprequest.ARGS.get('url')
    if not url:
        return HttpResponse('Bad Request', 400)
    url = urllib.unquote(url)

    jsoncb = httprequest.ARGS.get('callback')
    if jsoncb and not re.match(JSONCALLBACK_RE, jsoncb):
        return HttpResponse('Bad callback argument', 400)

    def _response(guids=(), message=None):
        content = {
            'guids': list(guids),
            'domain': getattr(spider, 'domain_name', None),
            'message': message,
        }
        return JsonResponse(content=content, callback=jsoncb)

    spider = spiders.fromurl(url)
    if not spider:
        return _response(message='No crawler found for site')

    if httprequest.ARGS.get('dontcrawl'):
        return _response()


    def _on_error(_failure):
        return _response(message='Error downloading url from site')

    def _on_success(pagedata):
        try:
            items = spider.identify(pagedata)
        except Exception, ex:
            return _response(message='Error processing url')

        guids = [i.guid for i in items if isinstance(i, ScrapedItem)]
        return _response(guids=guids)

    deferred = defer.Deferred().addCallbacks(_on_success, _on_error)
    request = Request(url=url, callback=deferred, dont_filter=True)
    schd = scrapyengine.schedule(request, spider)
    schd.chainDeferred(deferred)
    return deferred


urlmapping = (
    ('^ws/tools/url_to_guid/$', url_to_guid),
)


class UrlToGuidService(WebSite):
    def __init__(self):
        if not settings['WS_ENABLED']:
            raise NotConfigured

        port = settings.getint('WS_PORT') or 8088
        timeout = settings.getint('WS_TIMEOUT') or 15 # seconds
        resource = WebResource(urlmapping, timeout=timeout)
        WebSite.__init__(self, port=port, resource=resource)
