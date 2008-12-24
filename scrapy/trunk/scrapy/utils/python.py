"""
This module contains essential stuff that should've come with Python itself ;)
"""
import re
from sgmllib import SGMLParser

class FixedSGMLParser(SGMLParser):
    """The SGMLParser that comes with Python has a bug in the convert_charref()
    method. This is the same class with the bug fixed"""

    def convert_charref(self, name):
        """This method fixes a bug in Python's SGMLParser."""
        try:
            n = int(name)
        except ValueError:
            return
        if not 0 <= n <= 127 : # ASCII ends at 127, not 255
            return
        return self.convert_codepoint(n)


def flatten(x):
    """flatten(sequence) -> list

    Returns a single, flat list which contains all elements retrieved
    from the sequence and all recursively contained sub-sequences
    (iterables).

    Examples:
    >>> [1, 2, [3,4], (5,6)]
    [1, 2, [3, 4], (5, 6)]
    >>> flatten([[[1,2,3], (42,None)], [4,5], [6], 7, (8,9,10)])
    [1, 2, 3, 42, None, 4, 5, 6, 7, 8, 9, 10]"""

    result = []
    for el in x:
        if hasattr(el, "__iter__"):
            result.extend(flatten(el))
        else:
            result.append(el)
    return result


def unique(list_):
    """efficient function to uniquify a list preserving item order"""
    seen = {}
    result = []
    for item in list_:
        if item in seen: 
            continue
        seen[item] = 1
        result.append(item)
    return result


def str_to_unicode(text):
    if isinstance(text, str):
        return text.decode('utf-8')
    elif isinstance(text, unicode):
        return text
    else:
        raise TypeError('str_to_unicode can only receive a string object')

def unicode_to_str(text):
    if isinstance(text, unicode):
        return text.encode('utf-8')
    elif isinstance(text, str):
        return text
    else:
        raise TypeError('unicode_to_str can only receive a unicode object')

def re_rsearch(pattern, text, chunk_size=1024):
    """
    This function does a reverse search in a text using a regular expression
    given in the attribute 'pattern'.
    Since the re module does not provide this functionality, we have to find for
    the expression into chunks of text extracted from the end (for the sake of efficiency).
    At first, a chunk of 'chunk_size' kilobytes is extracted from the end, and searched for
    the pattern. If the pattern is not found, another chunk is extracted, and another
    search is performed.
    This process continues until a match is found, or until the whole file is read.
    In case the pattern wasn't found, None is returned, otherwise it returns a tuple containing
    the start position of the match, and the ending (regarding the entire text).
    """
    def _chunk_iter():
        offset = text_len = len(text)
        while True:
            offset -= (chunk_size * 1024)
            if offset <= 0:
                break
            yield (text[offset:], offset)
        yield (text, 0)

    pattern = re.compile(pattern) if isinstance(pattern, basestring) else pattern
    for chunk, offset in _chunk_iter():
        matches = [match for match in pattern.finditer(chunk)]
        if matches:
            return (offset + matches[-1].span()[0], offset + matches[-1].span()[1])
    return None

