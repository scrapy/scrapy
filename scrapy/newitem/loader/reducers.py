"""
This module provides some commonly used Reducers
"""

class TakeFirst(object):
    """Return the first non-null value from the list to reduce"""

    def __call__(self, values):
        for value in values:
            if value:
                return value


class Identity(object):
    """Return the list to reduce untouched"""

    def __call__(self, values):
        return values


class JoinStrings(object):
    """Return a string with the contents of the list to reduce joined with the
    separator given in the constructor, which defaults to u' '. 

    When using the default separator, this reducer is equivalent to the
    function: u' '.join 
    """

    def __init__(self, separator=u' '):
        self.separator = separator

    def __call__(self, values):
        return self.separator.join(values)
