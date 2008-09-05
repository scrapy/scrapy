"""
tagdepth metric

Compares pages analyzing a predefined set of (relevant)
tags and the depth where they appear in the page markup document. 

Requires ResponseSoup extension enabled.
"""

from __future__ import division

from BeautifulSoup import Tag

relevant_tags = set(['div', 'table', 'td', 'tr', 'h1','p'])

def get_symbol_dict(node, tags=(), depth=1):
    symdict = {}
    for tag in node:
        if isinstance(tag, Tag) and tag.name in tags:
            symbol = "%d%s" % (depth, str(tag.name))
            symdict[symbol] = symdict.setdefault(symbol, 0) + 1
            symdict.update(get_symbol_dict(tag, tags, depth+1))
    return symdict

def simhash(response, symnumbers=False):
    soup = response.soup
    symdict = get_symbol_dict(soup.find('body'), relevant_tags)
    if symnumbers:
        s = set([k+str(v) for k,v in symdict.items()])
    else:
        s = set(symdict.keys())
    return s

def compare(sh1, sh2):
    if sh1 == sh2:
        return 1.0
    else:
        return len(sh1 & sh2) / len(sh1 | sh2)

