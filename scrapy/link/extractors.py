# FIXME: code below is for backwards compatibility and should be removed before
# the 0.7 release

import warnings

from scrapy.contrib.linkextractors.sgml import SgmlLinkExtractor

class RegexLinkExtractor(SgmlLinkExtractor):

    def __init__(self, *args, **kwargs):
        warnings.warn("scrapy.link.extractors.RegexLinkExtractor is deprecated, use scrapy.contrib.linkextractors.sgml.SgmlLinkExtractor instead",
            DeprecationWarning, stacklevel=2)
        SgmlLinkExtractor.__init__(self, *args, **kwargs)

