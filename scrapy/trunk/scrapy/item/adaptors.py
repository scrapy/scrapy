import re
import cPickle as pickle

from traceback import format_exc
from urlparse import urlparse

from scrapy.xpath.selector import XPathSelector, XPathSelectorList
from scrapy.utils.python import unique, flatten
from scrapy.utils.markup import replace_tags, remove_entities
from scrapy.utils.misc import extract_regex
from scrapy.conf import settings
from scrapy import log

class AdaptorPipe(object):
    """
    Class that represents an item's attribute pipeline.

    This class contains a dictionary of attributes, matched with a list
    of adaptors to be run for filtering the input before storing.
    """

    def __init__(self, adaptors_pipe=None):
        """
        Receives a dictionary that maps attribute_name to a list of adaptor functions
        """
        self.pipes = adaptors_pipe or {}

    def set_adaptors(self, attr, adaptors):
        """
        Set the adaptor pipeline that will be used for the specified attribute
        """
        self.pipes[attr] = adaptors

    def execute(self, attrname, value, kwargs):
        """
        Execute pipeline for attribute name "attrname" and value "value".
        """
        debug = kwargs.get('debug') or all([settings.getbool('LOG_ENABLED'), settings.get('LOGLEVEL') == 'TRACE'])

        for adaptor in self.pipes.get(attrname, []):
            try:
                if debug:
                    print "  %07s | input >" % adaptor.__name__, repr(value)
                value = adaptor(kwargs)(value)
                if debug:
                    print "  %07s | output >" % adaptor.__name__, repr(value)
       
            except Exception, e:
                print "Error in '%s' adaptor. Traceback text:" % adaptor.__name__
                print format_exc()
                return
        
        return value

class AdaptorFunc(object):
    """
    This is the base class for adaptors.
    
    An adaptor is just an object subclassed from this class
    which defines the __call__ method, and receives/returns only
    one value.
    
    You can send the adaptor some extra options while creating it (just before running it)
    through **kwargs, and managing them by overriding the __init__ method, as shown on
    the UnquoteAdaptor, for example.
    """
    def __init__(self, kwargs={}):
        pass

    def __call__(self):
        raise NotImplementedError('You must define the __call__ method to create and use an adaptor')

############
# Adaptors #
############
class ExtractAdaptor(AdaptorFunc):
    """
    This adaptor extracts a list of strings
    from 'location', which can be either a list (or tuple),
    or an XPathSelector.
    
    This adaptor *always* returns a list.
    """

    def __call__(self, location):
        if not location:
            return []
        elif isinstance(location, (XPathSelector, XPathSelectorList)):
            return flatten(location.extract())
        elif isinstance(location, (list, tuple)):
            return flatten(map(lambda x: x.extract() if isinstance(x, (XPathSelector, XPathSelectorList)) else x, flatten(location)))
        elif isinstance(location, basestring):
            return [location]

class ExtractImagesAdaptor(AdaptorFunc):
    """
    This adaptor receives either an XPathSelector containing
    the desired locations for finding urls, or a tuple like (xpath, regexp)
    containing the xpath locations to look in, and a regular expression
    to parse those locations.
    
    In any case, this adaptor returns a list containing the absolute urls extracted.
    """

    def __init__(self, kwargs):
        self.base_url = kwargs.get('base_url')
        self.response = kwargs.get('response')
        if not self.response and not self.base_url:
            raise AttributeError('You must specify either a response or a base_url to the ExtractImages adaptor.')

    def extract_from_xpath(self, selector):
        ret = []

        if selector.xmlNode.type == 'element':
          if selector.xmlNode.name == 'a':
              children = selector.x('child::*')
              if len(children) > 1:
                ret.extend(selector.x('.//@href'))
                ret.extend(selector.x('.//@src'))
              elif len(children) == 1 and children[0].xmlNode.name == 'img':
                ret.extend(children.x('@src'))
              else:
                ret.extend(selector.x('@href'))
          elif selector.xmlNode.name == 'img':
            ret.extend(selector.x('@src'))
          else:
            ret.extend(selector.x('.//@href'))
            ret.extend(selector.x('.//@src'))
        elif selector.xmlNode.type == 'attribute' and selector.xmlNode.name in ['href', 'src']:
            ret.append(selector)
        
        return ret

    def absolutize_link(self, base_url, link):
        base_url = urlparse(base_url)
        ret = []

        if link.startswith('/'):
            ret.append('http://%s%s' % (base_url.hostname, link))
        elif link.startswith('http://'):
            ret.append(link)
        else:
            ret.append('http://%s%s/%s' % (base_url.hostname, base_url.path, link))

        return ret

    def __call__(self, locations):
        rel_links = []
        for location in flatten(locations):
            if isinstance(location, (XPathSelector, XPathSelectorList)):
                rel_links.extend(self.extract_from_xpath(location))
            else:
                rel_links.append(location)
        rel_links = ExtractAdaptor()(rel_links)
        
        if self.response:
            return flatten([self.absolutize_link(self.response.url, link) for link in rel_links])
        elif self.base_url:
            return flatten([self.absolutize_link(self.base_url, link) for link in rel_links])
        else:
            abs_links = []
            for link in rel_links:
                if link.startswith('http://'):
                    abs_links.append(link)
                else:
                    log.msg('Couldnt get the absolute url for "%s". Ignoring link...' % link, 'WARNING')
            return abs_links
                
class BoolAdaptor(AdaptorFunc):
    def __call__(self, value):
        return bool(value)

class ToUnicodeAdaptor(AdaptorFunc):
    """
    Receives a list of strings, converts
    it to unicode, and returns a new list.
    """
    
    def __call__(self, value):
        if isinstance(value, (list, tuple)):
            return [ unicode(v) for v in value ]
        else:
            raise TypeError('ToUnicodeAdaptor must receive either a list or a tuple.')
    
class RegexAdaptor(AdaptorFunc):
    """
    This adaptor must receive either a list of strings or an XPathSelector
    and return a new list with the matches of the given strings with the given regular
    expression (which is passed by a keyword argument, and is mandatory for this adaptor).
    """
    
    def __init__(self, kwargs):
        self.regex = kwargs.get('regex')

    def __call__(self, value):
        if self.regex:
            if isinstance(value, (XPathSelector, XPathSelectorList)):
                return value.re(self.regex)
            elif isinstance(value, list) and value:
                return flatten([extract_regex(self.regex, string, 'utf-8') for string in value])
        return value

class UnquoteAdaptor(AdaptorFunc):
    """
    Receives a list of strings, removes all of the
    entities the strings may have, and returns
    a new list
    """

    def __init__(self, kwargs={}):
        self.keep = kwargs.get('keep', ['lt', 'amp'])

    def __call__(self, value):
        return [ remove_entities(v, keep=self.keep) for v in value ]

class RemoveTagsAdaptor(AdaptorFunc):
    def __call__(self, value):
        return [ replace_tags(v) for v in value ]
    
class RemoveRootAdaptor(AdaptorFunc):
    _remove_root_re = re.compile(r'^\s*<.*?>(.*)</.*>\s*$', re.DOTALL)
    def _remove_root(self, value):
        m = self._remove_root_re.search(value)
        if m:
            value = m.group(1)
        return value

    def __call__(self, value):
        return [ self._remove_root(v) for v in value ]
    
class CleanSpacesAdaptor(AdaptorFunc):
    _clean_spaces_re = re.compile("\s+", re.U)
    def __call__(self, value):
        return [ self._clean_spaces_re.sub(' ', v) for v in value ]

class StripAdaptor(AdaptorFunc):
    def __call__(self, value):
        return [ v.strip() for v in value ]

class DropEmptyAdaptor(AdaptorFunc):
    def __call__(self, value):
        return [ v for v in value if v ]

class DelistAdaptor(AdaptorFunc):
    def __init__(self, kwargs={}):
        self.delimiter = kwargs.get('join_delimiter', ' ')

    def __call__(self, value):
        return self.delimiter.join(value)
    
class PickleAdaptor(AdaptorFunc):
    def __call__(self, value):
        return pickle.dumps(value)

class DePickleAdaptor(AdaptorFunc):
    def __call__(self, value):
        return pickle.loads(value)

class UniqueAdaptor(AdaptorFunc):
    def __call__(self, value):
        return unique(value)

class FlattenAdaptor(AdaptorFunc):
    def __call__(self, value):
        return flatten(value)

#############
# Pipelines #
#############
"""
The following methods automatically generate adaptor pipelines
for some basic datatypes, according to the parameters you pass them.
"""
def single_pipeline(do_remove_root=True, do_remove_tags=True, do_unquote=True):
    pipe = [ ExtractAdaptor,
             UniqueAdaptor,
             ToUnicodeAdaptor,
             DropEmptyAdaptor,
             CleanSpacesAdaptor,
             StripAdaptor,
           ]

    if do_remove_root:
        pipe.insert(4, RemoveRootAdaptor)
    if do_remove_tags:
        pipe.insert(5, RemoveTagsAdaptor)
    if do_unquote:
        pipe.append(UnquoteAdaptor)
    return pipe + [DelistAdaptor]
           
def url_pipeline():
    return [ ExtractImagesAdaptor,
             UniqueAdaptor,
             ToUnicodeAdaptor,
             DropEmptyAdaptor,
           ]
               
list_pipeline = [ ExtractAdaptor,
                  UniqueAdaptor,
                  ToUnicodeAdaptor,
                  DropEmptyAdaptor,
                  UnquoteAdaptor,
                  RemoveTagsAdaptor,
                  RemoveRootAdaptor,
                  StripAdaptor,
                ]
                
list_join_pipeline = list_pipeline + [DelistAdaptor]
