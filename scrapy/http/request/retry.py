"""
This module implements the RetryRequest class which is a way to issue a retry attempt
on a request that failed temporarily such as a ban or missing content
"""
from scrapy.utils.trackref import object_ref


class RetryRequest(object_ref):
    def __init__(self, request, *args, **kwargs):
        self.request = request
        self.reason = kwargs.get('reason')
