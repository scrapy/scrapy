#!/usr/bin/env python
from __future__ import division

from BeautifulSoup import BeautifulSoup, Tag

relevant_tags = ['div', 'table', 'td', 'tr', 'h1']

def get_symbol_dict(node, tags=(), depth=1):
    symdict = {}
    for tag in node:
        if isinstance(tag, Tag) and tag.name in tags:
            symbol = str("%d%s" % (depth, tag.name))
            symdict[symbol] = symdict.setdefault(symbol, 0) + 1
            symdict.update(get_symbol_dict(tag, tags, depth+1))
    return symdict

def simhash(response):
    soup = BeautifulSoup(response.body.to_string())
    symdict = get_symbol_dict(soup.find('body'), relevant_tags)
    return set(symdict.keys())

def compare(fp1, fp2):
    return len(fp1 & fp2) / len(fp1 | fp2)
