# -*- coding: utf-8 -*-

import re
from scrapy.xpath.selector import XPathSelector, XPathSelectorList
from scrapy.utils.url import canonicalize_url
from scrapy.utils.misc import extract_regex
from scrapy.utils.python import flatten, str_to_unicode
from scrapy.item.adaptors import adaptize

def to_unicode(value):
    """
    Receives a list of strings, converts
    it to unicode, and returns a new list.
    E.g:
      >> to_unicode(['it costs 20€, or 30£'])
        [u'it costs 20\u20ac, or 30\xa3']

    Input: iterable of strings
    Output: list of unicodes
    """
    if hasattr(value, '__iter__'):
        return [ str_to_unicode(v) if isinstance(v, basestring) else str_to_unicode(str(v)) for v in value ]
    else:
        raise TypeError('to_unicode must receive an iterable.')

def clean_spaces(value):
    """
    Converts multispaces into single spaces for each string
    in the provided iterable.
    E.g:
      >> clean_spaces(['Hello   sir'])
      [u'Hello sir']

    Input: iterable of unicodes
    Output: list of unicodes
    """
    _clean_spaces_re = re.compile("\s+", re.U)
    return [ _clean_spaces_re.sub(' ', v.decode('utf-8')) for v in value ]

def strip(value):
    """
    Removes any spaces at both the start and the ending
    of the provided string or list.
    E.g:
      >> strip([' hi   ', 'buddies  '])
      [u'hi', u'buddies']
      >> strip(' hi buddies    ')
      u'hi buddies'

    Input: unicode or iterable of unicodes
    Output: unicode or list of unicodes
    """
    if isinstance(value, basestring):
        return unicode(value.strip())
    elif hasattr(value, '__iter__'):
        return [ unicode(v.strip()) for v in value ]

def drop_empty(value):
    """
    Removes any index that evaluates to None
    from the provided iterable.
    E.g:
      >> drop_empty([0, 'this', None, 'is', False, 'an example'])
      ['this', 'is', 'an example'] 

    Input: iterable
    Output: list
    """
    return [ v for v in value if v ]

def canonicalize_urls(value):
    """
    Canonicalizes each url in the list you provide.
    To see what this implies, check out canonicalize_url's
    docstring, at scrapy.utils.url.py

    Input: iterable of unicodes(urls)
    Output: list of unicodes(urls)
    """
    if hasattr(value, '__iter__'):
        return [canonicalize_url(str(url)) for url in value]
    elif isinstance(value, basestring):
        return canonicalize_url(str(value))
    return ''

class Delist(object):
    """
    Joins a list with the specified delimiter
    in the adaptor's constructor.

    Input: iterable of strings
    Output: unicode
    """
    def __init__(self, delimiter=' '):
        self.delimiter = delimiter
    
    def __call__(self, value, delimiter=None):
        if delimiter is not None:
            self.delimiter = delimiter
        return self.delimiter.join(value)

class Regex(object):
    """
    This adaptor must receive either a list of strings or an XPathSelector
    and return a new list with the matches of the given strings with the given regular
    expression (which is passed by a keyword argument, and is mandatory for this adaptor).

    Input: XPathSelector, XPathSelectorList, iterable
    Output: list of unicodes
    """
    def __init__(self, regex=r''):
        self.regex = regex

    def __call__(self, value):
        if self.regex:
            if isinstance(value, (XPathSelector, XPathSelectorList)):
                return value.re(self.regex)
            elif hasattr(value, '__iter__'):
                return flatten([extract_regex(self.regex, string, 'utf-8') for string in value])
        return value

