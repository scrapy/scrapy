"""
This module contains essential stuff that should've come with Python itself ;)
"""

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


