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

    def function(self, attrname, location, **pipeargs):
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
        
   
_clean_spaces_re = re.compile("\s+", re.U)
_remove_root_re = re.compile(r'^\s*<.*?>(.*)</.*>\s*$', re.DOTALL)
_xml_remove_tags_re = re.compile(r'<[a-zA-Z\/!][^>]*?>')
_xml_remove_cdata_re = re.compile('<!\[CDATA\[(.*)\]\]', re.S)
_xml_cdata_split_re = re.compile('(<!\[CDATA\[.*?\]\]>)', re.S)

class HtmlCleanAdaptor(ExtendedAdaptor):

    def function(self, attrname, string, **pipeargs):
        return self.do(self.clean, string, **pipeargs)
    
    def clean(self, string, **kwargs):
        """Clean (list of) strings removing newlines, spaces, etc"""
        if isinstance(string, list):
            return [self.clean(s, **kwargs) for s in string]
        
        xml = self._remove_tags(string, **kwargs)

        if kwargs.get('remove_root', True) and not kwargs.get('remove_tags', True):
            m = _remove_root_re.search(xml)
            if m:
                xml = m.group(1)

        if kwargs.get('remove_spaces', True):
            xml = _clean_spaces_re.sub(' ', xml)
        if kwargs.get('strip', True):
            xml = xml.strip()
    
        return xml
    
    def _remove_tags(self, xml, **kwargs):
        if kwargs.get('remove_tags', True):
            xml = _xml_remove_tags_re.sub(' ', xml)
        return xml
        
class XmlCleanAdaptor(HtmlCleanAdaptor):
    
    def _remove_tags(self, xml, **kwargs):
        #process in pieces the text that contains CDATA. The first check is to avoid unnecesary regex check
        if _xml_remove_cdata_re.search(xml):
            pieces = []
            
            for piece in _xml_cdata_split_re.split(xml):
                
                m = _xml_remove_cdata_re.search(piece)
                if m:
                    if kwargs.get('remove_cdata', True):#remove cdata special tag
                        pieces.append(HtmlCleanAdaptor._remove_tags(self, m.groups()[0], **kwargs))
                    else:
                        pieces.append(piece)#conserve intact the cdata
                else:
                    pieces.append(HtmlCleanAdaptor._remove_tags(self, piece, **kwargs))

            xml = "".join(pieces)
        else:
            xml = HtmlCleanAdaptor._remove_tags(self, xml, **kwargs)
        return xml
