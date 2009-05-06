# -*- coding: utf-8 -*-

import re
from scrapy.xpath.selector import XPathSelector, XPathSelectorList
from scrapy.utils.misc import extract_regex
from scrapy.utils.python import flatten, str_to_unicode, unicode_to_str
from scrapy.item.adaptors import adaptize

def to_unicode(value, adaptor_args):
    """
    Receives a string and converts it to unicode
    using the given encoding (if specified, else utf-8 is used)
    and returns a new unicode object.
    E.g:
      >> to_unicode('it costs 20\xe2\x82\xac, or 30\xc2\xa3')
        [u'it costs 20\u20ac, or 30\xa3']

    Input: string
    Output: unicode
    """
    if not isinstance(value, basestring):
        value = str(value)
    return str_to_unicode(value, adaptor_args.get('encoding', 'utf-8'))

_clean_spaces_re = re.compile("\s+", re.U)
def clean_spaces(value):
    """
    Converts multispaces into single spaces for the given string.
    E.g:
      >> clean_spaces(u'Hello   sir')
      u'Hello sir'

    Input: string/unicode
    Output: unicode
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

def delist(delimiter=''):
    """
    This factory returns and adaptor that joins
    an iterable with the specified delimiter.

    Input: iterable of strings/unicodes
    Output: string/unicode
    """
    def delist(value, adaptor_args):
        delim = adaptor_args.get('join_delimiter', delimiter)
        return delim.join(value)
    return delist

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

