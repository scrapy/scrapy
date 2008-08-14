"""
Adaptors for item adaptation pipe.
"""

from scrapy.item.models import BaseAdaptor
from scrapy.utils.python import flatten, unique
from scrapy.xpath import XPathSelector
from scrapy.utils.misc import unquote_html, location_str
from scrapy.conf import settings

class ExtendedAdaptor(BaseAdaptor):

    def do(self, function, a, *args, **kwargs):
        """Execute a function of the pipeline examining kwargs for possible 
        pre/post functions. Also prints a lot of useful debugging info."""
    
        debug = kwargs.get('debug')
        fname = function.__name__
        f = kwargs.get('pre_%s' % fname)
        if f and a:
            if debug:
                print "  pre_%s | input  >" % fname, a
            a = f(a)
            if debug:
                print "  pre_%s | output >" % fname, a
    
        if debug:
            print repr(kwargs)
            print "  %07s | input >" % fname, location_str(a)
        a = function(a, *args, **kwargs)
        if debug:
            print "  %07s | output>" % fname, a
    
        f = kwargs.get('post_%s' % fname)
        if f and a:
            if debug:
                print "  post_%s | input  >" % fname, a
            a = f(a)
            if debug:
                print "  post_%s | output >" % fname, a
        return a
        
class ExtractAdaptor(ExtendedAdaptor):

    def function(self, item, attrname, location, **pipeargs):
        return self.do(self._extract, location, **pipeargs)

    def _extract(self, location, **kwargs):
        """Extract a list of strings from the location passed.
        Receives a list of XPathSelectors or an XPathSelector,
        or a list of strings or a string.
        
        Return a list of strings extracted.

        This function *always* returns a list.
        """
        if not location:
            return []
        if isinstance(location, (list, tuple)):
            strings = flatten([self._extract(o, **kwargs) for o in location])
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
        
