from __future__ import absolute_import

import warnings
from scrapy.exceptions import ScrapyDeprecationWarning

from twisted.web import client
from twisted.internet import endpoints

Agent = client.Agent  # since < 11.1
ProxyAgent = client.ProxyAgent  # since 11.1
ResponseDone = client.ResponseDone  # since 11.1
ResponseFailed = client.ResponseFailed  # since 11.1
HTTPConnectionPool = client.HTTPConnectionPool  # since 12.1
TCP4ClientEndpoint = endpoints.TCP4ClientEndpoint  # since 10.1

warnings.warn("Importing from scrapy.xlib.tx is deprecated and will"
              " no longer be supported in future Scrapy versions."
              " Update your code to import from twisted proper.",
              ScrapyDeprecationWarning, stacklevel=2)
