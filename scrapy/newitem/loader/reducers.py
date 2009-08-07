"""
This module provides some commonly used Reducers.

See documentation in docs/topics/newitem-loader.rst
"""

class TakeFirst(object):

    def __call__(self, values):
        for value in values:
            if value:
                return value


class Identity(object):

    def __call__(self, values):
        return values


class Join(object):

    def __init__(self, separator=u' '):
        self.separator = separator

    def __call__(self, values):
        return self.separator.join(values)
