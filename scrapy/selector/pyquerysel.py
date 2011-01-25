"""
PyQuery selector
"""

from pyquery import PyQuery
from scrapy.utils.trackref import object_ref

"""
This is added because it will complain that XPathSelector doesn't exist 
without it.
"""
from scrapy.selector.dummysel import *

class PyQuerySelector(object_ref):

    def __init__(self, response):
        self.response = response.body
        self.pq = PyQuery(self.response)
        
    def __call__(self, query):
        return self.pq(query)
        
