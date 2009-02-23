"""
Monkey patches

These are generally a bad idea.
"""
import twisted
from twisted.web.client import HTTPClientFactory


# Extend limit for BeautifulSoup parsing loops
#import sys
#sys.setrecursionlimit(7400)

def apply_patches():
    if twisted.__version__ < '8.0.0':
        patch_HTTPPageGetter_handleResponse()


# bugfix not present in twisted 2.5 for handling empty response of HEAD requests
def patch_HTTPPageGetter_handleResponse():
    from twisted.web.client import PartialDownloadError, HTTPPageGetter
    from twisted.python import failure
    from twisted.web import error

    def _handleResponse(self, response):
        if self.quietLoss:
            return
        if self.failed:
            self.factory.noPage(
                failure.Failure(
                    error.Error(
                        self.status, self.message, response)))
        if self.factory.method.upper() == 'HEAD':
            # Callback with empty string, since there is never a response
            # body for HEAD requests.
            self.factory.page('')
        elif self.length != None and self.length != 0:
            self.factory.noPage(failure.Failure(
                PartialDownloadError(self.status, self.message, response)))
        else:
            self.factory.page(response)
        # server might be stupid and not close connection. admittedly
        # the fact we do only one request per connection is also
        # stupid...
        self.transport.loseConnection()
    setattr(HTTPPageGetter, 'handleResponse', _handleResponse)
