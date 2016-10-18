# -*- coding: utf-8 -*-
"""
    sphinx.util.jsonimpl
    ~~~~~~~~~~~~~~~~~~~~

    JSON serializer implementation wrapper.

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

import json

from six import text_type
from six.moves import UserString


class SphinxJSONEncoder(json.JSONEncoder):
    """JSONEncoder subclass that forces translation proxies."""
    def default(self, obj):
        if isinstance(obj, UserString):
            return text_type(obj)
        return json.JSONEncoder.default(self, obj)


def dump(obj, fp, *args, **kwds):
    kwds['cls'] = SphinxJSONEncoder
    return json.dump(obj, fp, *args, **kwds)


def dumps(obj, *args, **kwds):
    kwds['cls'] = SphinxJSONEncoder
    return json.dumps(obj, *args, **kwds)


def load(*args, **kwds):
    return json.load(*args, **kwds)


def loads(*args, **kwds):
    return json.loads(*args, **kwds)
