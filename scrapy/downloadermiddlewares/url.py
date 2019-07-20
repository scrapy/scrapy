""" This module implements the URLMiddleware which does any needed operations on the url 
    like changing backslashes to forwardslashes
"""

from scrapy import signals


class URLMiddleware(object):
    """ This middleware does any needed operations on the url 
    like changing backslashes to forwardslashes
    """

    def process_request(self, request, spider):
        new_url = request.url.replace('\\','/')
        if new_url == request.url:
            return
        return request.replace(url = new_url)
        

