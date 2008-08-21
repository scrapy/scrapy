"""
Generic Adaptors for item adaptation pipe. Performs tasks
usually needed by most cases
"""

import re

from scrapy.item.models import BaseAdaptor
from scrapy.utils.python import flatten, unique
from scrapy.xpath import XPathSelector
from scrapy.utils.misc import unquote_html, location_str
from scrapy.conf import settings
from scrapy.utils.markup import clean_markup

class ExtendedAdaptor(BaseAdaptor):

    def do(self, function, a, *args, **kwargs):
        """Executes an adaptor printing a lot of useful debugging info."""
    
        debug = kwargs.get('debug')
        fname = function.__name__
    
        if debug:
            print repr(kwargs)
            print "  %07s | input >" % fname, location_str(a)
        a = function(a, *args, **kwargs)
        if debug:
            print "  %07s | output>" % fname, a
    
        return a
        
class ExtractAdaptor(ExtendedAdaptor):

    def function(self, location, **pipeargs):
        return self.do(self.extract, location, **pipeargs)
    
    def extract(self, location, **kwargs):
        """Extract a list of strings from the location passed.
        Receives a list of XPathSelectors or an XPathSelector,
        or a list of strings or a string.
        
        Return a list of strings extracted.

        This function *always* returns a list.
        """
        if not location:
            return []
        if isinstance(location, (list, tuple)):
            strings = flatten([self.extract(o, **kwargs) for o in location])
            if kwargs.get('remove_dupes', False):
                strings = unique(strings)
            if kwargs.get('first', False):
                return strings[:1]
            else:
                return strings
        # XPathSelector
        elif isinstance(location, XPathSelector):
            strings = [location.extract()]
        # Strings
        elif isinstance(location, unicode):
            strings = [unquote_html(location, keep_reserved=True)]
        elif isinstance(location, str):
            encoding = kwargs.get("encoding", settings.get('DEFAULT_DATA_ENCODING'))
            strings = [unquote_html(unicode(location, encoding), keep_reserved=True)]
        else:
            raise TypeError, "unsupported location type: %s" % type(location)

        return strings

class HtmlCleanAdaptor(ExtendedAdaptor):

    def function(self, string, **pipeargs):
        return self.do(self.clean, string, **pipeargs)
    
    def clean(self, string, **pipeargs):
        return clean_markup(string, **pipeargs)
        
class XmlCleanAdaptor(HtmlCleanAdaptor):
    
    def clean(self, string, **pipeargs):
        pipeargs["xml_doc"] = True
        return clean_markup(string, **pipeargs)
