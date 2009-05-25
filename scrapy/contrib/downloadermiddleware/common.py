
import warnings

from scrapy.contrib.downloadermiddleware.defaultheaders import DefaultHeadersMiddleware

class CommonMiddleware(DefaultHeadersMiddleware):

    def __init__(self):
        warnings.warn("scrapy.contrib.downloadermiddleware.common.CommonMiddleware has been replaced by scrapy.contrib.downloadermiddleware.defaultheaders.DefaultHeadersMiddleware")
        DefaultHeadersMiddleware.__init__(self)
