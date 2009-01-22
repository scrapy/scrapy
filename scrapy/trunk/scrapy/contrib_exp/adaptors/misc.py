# -*- coding: utf-8 -*-

import re
from scrapy.xpath.selector import XPathSelector, XPathSelectorList
from scrapy.utils.misc import extract_regex
from scrapy.utils.python import flatten, str_to_unicode, unicode_to_str
from scrapy.item.adaptors import adaptize

def to_unicode(value, adaptor_args):
    """
    Receives a list of strings, converts
    it to unicode, and returns a new list.
    E.g:
      >> to_unicode(['it costs 20€, or 30£'])
        [u'it costs 20\u20ac, or 30\xa3']

    Input: iterable of strings
    Output: list of unicodes
    """
    if not isinstance(value, basestring):
        value = str(value)
    return str_to_unicode(value, adaptor_args.get('encoding', 'utf-8'))

_clean_spaces_re = re.compile("\s+", re.U)
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
    return _clean_spaces_re.sub(' ', str_to_unicode(value))

def strip(value):
    """
    Removes any spaces at both the start and the ending
    of the provided string.
    E.g:
      >> strip(' hi buddies    ')
      u'hi buddies'

    Input: string/unicode
    Output: string/unicode
    """
    return value.strip()

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

class Delist(object):
    """
    Joins a list with the specified delimiter
    in the adaptor's constructor.

    Input: iterable of strings/unicodes
    Output: string/unicode
    """
    def __init__(self, delimiter=''):
        self.delimiter = delimiter

    def __call__(self, value, adaptor_args):
        delimiter = adaptor_args.get('join_delimiter', self.delimiter)
        return delimiter.join(value)

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

