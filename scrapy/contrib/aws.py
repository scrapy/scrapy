"""
A downloader middleware for signing AWS requests just before they get into the
downloader. It is important to sign as close to the downloader as possible
because Amazon Web Service use timestamps for authentication.
"""

import os
from time import strftime, gmtime
from scrapy.utils.aws import sign_request
from scrapy.conf import settings


class AWSMiddleware(object):

    def __init__(self):
        self.access_key = settings['AWS_ACCESS_KEY_ID'] or \
            os.environ.get('AWS_ACCESS_KEY_ID')
        self.secret_key = settings['AWS_SECRET_ACCESS_KEY'] or \
            os.environ.get('AWS_SECRET_ACCESS_KEY')

    def process_request(self, request, spider):
        if request.meta.get('sign_s3_request'):
            request.headers['Date'] = strftime("%a, %d %b %Y %H:%M:%S GMT", gmtime())
            sign_request(request, self.access_key, self.secret_key)
