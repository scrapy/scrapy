from functools import partial
from scrapy.core.exceptions import NotConfigured
from scrapy.utils.serialization import serialize
from scrapy.conf import settings

from .site import WebSite,  WebResource
from .json import JsonResponse

STATS_WSPORT = settings.getint('STATS_WSPORT', 8089)
STATS_WSTIMEOUT = settings.getint('STATS_WSTIMEOUT', 15)

jsonserialize = partial(serialize, format='json')


def stats(request):
    service = request.ARGS.get('service', 'getstats')
    if service == 'getstats':
        domain = request.ARGS.get('domain')
        count = request.ARGS.get('count', 1)
        if not domain:
            path = request.ARGS.get('path')
            offset = request.ARGS.get('offset')
            order = request.ARGS.get('order', 'domain')
            olist = request.ARGS.get('olist', 'ASC')

    from scrapy.store.db import DomainDataHistory
    ddh = DomainDataHistory(settings['SCRAPING_DB'], 'domain_data_history')

    if service == 'countdomains':
        stats = [ddh.domain_count()]
    elif domain:
        stats = list(ddh.get(domain, count=int(count)))
    else:
        stats = list(ddh.getlast_alldomains(count, offset, order, olist, path=path))

    content = {'data': stats if stats else "No stats found"}
    return JsonResponse(content=content, serialize=jsonserialize)


urlmapping = (
        ('^ws/tools/stats/$', stats),
        )


class StatsService(WebSite):
    def __init__(self):
        if not settings['WS_ENABLED']:
            raise NotConfigured

        if not settings['SCRAPING_DB']:
            print "SCRAPING_DB setting is required for the stats web service"
            raise NotConfigured

        resource = WebResource(urlmapping, timeout=STATS_WSTIMEOUT)
        WebSite.__init__(self, port=STATS_WSPORT, resource=resource)
