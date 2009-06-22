"""
Dns cache module. 
This module implements a dns cache to improve the performance of the 
crawler, reducing the dns lookups.
"""
import socket
from scrapy.core import signals
from pydispatch import dispatcher

class DNSCache(object):
    """
    DNSCache.

    Impelements a DNS Cache to improve the performance of the 
    DNS lookup that the crawler request when it's running.
    Use:
     Create a single instance:
       >>> import dnscache
       >>> cachedns = dnscache.DNSCache()
     
     To get (and set a new host if not exists) we only call 
       >> ip = cachedns.get('python.org')
       >>> print ip
       '82.94.164.162'
       >>> 
    """
    def __init__(self):
        dispatcher.connect(self.domain_closed, signal=signals.domain_closed)
        self._cache = {}
    
    def get(self, host):
        """
        Returns the ip associated with the host and save it in
        the cache.
        """
        try:
            ips = self._cache[host]
        except KeyError:
            # The socket.gethostbyname_ex throw an
            # exception when it can't get the host 
            # ip. So we save the hostname anyway.
            # we use socket.getaddrinfo that support IP4/IP6
            try:
                ips = list(set([x[4][0] for x in socket.getaddrinfo(host,None)])) 
            except socket.gaierror:
                ips = [host]
            self._cache[host] = ips
        return ips[0]

    def domain_closed(self, domain, spider, reason):
        if domain in self._cache:
            del self._cache[domain]
