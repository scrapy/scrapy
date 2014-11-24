from scrapy import twisted_version
if twisted_version > (13, 0, 0):
    from twisted.web import client
    from twisted.internet import endpoints
if twisted_version >= (11, 1, 0):
    from . import client, endpoints
else:
    from scrapy.exceptions import NotSupported
    class _Mocked(object):
        def __init__(self, *args, **kw):
            raise NotSupported('HTTP1.1 not supported')
    class _Mock(object):
        def __getattr__(self, name):
            return _Mocked
    client = endpoints = _Mock()


Agent = client.Agent
ProxyAgent = client.ProxyAgent
ResponseDone = client.ResponseDone
ResponseFailed = client.ResponseFailed
HTTPConnectionPool = client.HTTPConnectionPool
TCP4ClientEndpoint = endpoints.TCP4ClientEndpoint
