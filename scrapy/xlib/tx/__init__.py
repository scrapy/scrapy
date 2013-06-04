import twisted
if twisted.__version__.split('.') < (13, 0, 1):
    from . import client, endpoints
else:
    from twisted.web import client
    from twisted.internet import endpoints


Agent = client.Agent
ProxyAgent = client.ProxyAgent
ResponseDone = client.ResponseDone
ResponseFailed = client.ResponseFailed
HTTPConnectionPool = client.HTTPConnectionPool
TCP4ClientEndpoint = endpoints.TCP4ClientEndpoint
