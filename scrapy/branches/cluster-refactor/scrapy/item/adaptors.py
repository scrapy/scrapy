import re

from traceback import format_exc

from scrapy.xpath.selector import XPathSelector, XPathSelectorList
from scrapy.utils.python import unique, flatten
from scrapy.utils.markup import replace_tags, remove_entities
from scrapy.utils.misc import extract_regex

class AdaptorPipe:
    def __init__(self, adaptors_pipe=None):
        """
        Receives a dictionary that maps attribute_name to a list of adaptor functions
        """
        self.pipes = adaptors_pipe or {}

    def append_adaptor(self, attrname, adaptor):
        """
        Add an adaptor at the end of the provided attribute's pipeline
        """
        if callable(adaptor):
            if self.pipes.get(attrname):
                self.pipes[attrname].append(adaptor)
            else:
                self.pipes[attrname] = [adaptor]
                
    def execute(self, attrname, value, debug=False):
        """
        Execute pipeline for attribute name "attrname" and value "value".
        """
        for function in self.pipes.get(attrname, []):
            try:
                if debug:
                    print "  %07s | input >" % function.func_name, repr(value)
                value = function(value)
                if debug:
                    print "  %07s | output>" % function.func_name, repr(value)

            except Exception, e:
                print "Error in '%s' adaptor. Traceback text:" % function.func_name
                print format_exc()
                return

        return value


############
# Adaptors #
############
def extract(location):
    """
    This adaptor extracts a list of strings
    from 'location', which can be either a list (or tuple),
    or an XPathSelector.
    
    This function *always* returns a list.
    """
    if not location:
        return []
    elif isinstance(location, XPathSelectorList):
        return flatten([extract(o) for o in location])
    elif isinstance(location, XPathSelector):
        return location.extract()
    elif isinstance(location, (list, tuple)):
        return flatten(location)
    elif isinstance(location, basestring):
        return [location]

def _absolutize_links(rel_links, current_url, base_url):
    abs_links = []
    for link in rel_links:
        if link.startswith('/'):
            abs_links.append('%s%s' % (base_url, link))
        elif link.startswith('http://'):
            abs_links.append(link)
        else:
            abs_links.append('%s/%s' % (current_url, link))
    return abs_links
    
def extract_links(locations):
    """
    This adaptor receives either an XPathSelector containing
    the desired locations for finding urls, or a tuple like (xpath, regexp)
    containing the xpath locations to look in, and a regular expression
    to parse those locations.
    
    In any case, this adaptor returns a list of absolute urls extracted.
    """
    ret = []
    if locations:
        regexp = None
        if isinstance(locations, XPathSelector):
            locations = XPathSelectorList([locations])
        elif isinstance(locations, tuple):
            locations, regexp = locations
    
        if isinstance(locations, XPathSelectorList):
            if regexp:
                ret = locations.re(regexp)
            else:
                for selector in locations:
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
                ret = [selector.extract() for selector in ret]
            current_url, base_url = re.search(r'((http://(?:www\.)?[\w\d\.-]+?)(?:/|$).*)', locations[0].response.url).groups()
            ret = _absolutize_links(ret, current_url, base_url)
    return ret

def to_unicode(value):
    """
    Receives a list of strings, converts
    it to unicode, and returns a new list.
    """
    if isinstance(value, (list, tuple)):
        return [ unicode(v) for v in value ]
    else:
        raise TypeError('to_unicode adaptor must receive a list or a tuple.')
    
def regex(expr):
    """
    This factory function returns a ready-to-use
    adaptor for the specified regular expression.
    This adaptor will accept either an XPathSelectorList
    or a list of strings, and will apply the provided regular
    expression to each of its members.
    
    This adaptor always returns a list of strings.
    """
    def _regex(value):
        if isinstance(value, (XPathSelector, XPathSelectorList)):
            return value.re(expr)
        elif isinstance(value, list) and value:
            return flatten([extract_regex(expr, string, 'utf-8') for string in value])
        return value
    return _regex

def unquote_all(value):
    """
    Receives a list of strings, removes all of the
    entities the strings may have, and returns
    a new list
    """
    return [ remove_entities(v) for v in value ]

def unquote(value):
    """
    Receives a list of strings, removes all of the entities
    the strings may have (except for &lt; and &amp;), and
    returns a new list
    """
    return [ remove_entities(v, keep=['lt', 'amp']) for v in value ]

def remove_tags(value):
    return [ replace_tags(v) for v in value ]
    
_remove_root_re = re.compile(r'^\s*<.*?>(.*)</.*>\s*$', re.DOTALL)
def _remove_root(value):
    m = _remove_root_re.search(value)
    if m:
        value = m.group(1)
    return value

def remove_root(value):
    return [ _remove_root(v) for v in value ]
    
_clean_spaces_re = re.compile("\s+", re.U)
def remove_multispaces(value):
    return [ _clean_spaces_re.sub(' ', v) for v in value ]

def strip(value):
    return [ v.strip() for v in value ]

def drop_empty_elements(value):
    return [ v for v in value if v ]

def delist(value):
    return ' '.join(value)
    


#############
# Pipelines #
#############
"""
The following methods automatically generate adaptor pipelines
for some basic datatypes, according to the parameters you pass them.
"""
def single_pipeline(remove_root=True, remove_tags=True, do_unquote=True):
    pipe = [ extract,
             unique,
             to_unicode,
             drop_empty_elements,
             remove_multispaces,
             strip,
           ]
    if remove_root:
        pipe.insert(4, remove_root)
    if remove_tags:
        pipe.insert(5, remove_tags)
    if do_unquote:
        pipe.append(unquote)
    return pipe + [delist]
           
def url_pipeline():
    return [ extract_links,
             unique,
             to_unicode,
             drop_empty_elements,
           ]
               
def list_pipeline(do_extract=True):
    pipe = []
    if do_extract:
        pipe.append(extract)
    return pipe + [ unique,
                    to_unicode,
                    drop_empty_elements,
                    unquote,
                    remove_tags,
                    remove_root,
                    strip,
                  ]
                
def list_join_pipeline(delimiter='\t'):
    return list_pipeline() + [delimiter.join]

