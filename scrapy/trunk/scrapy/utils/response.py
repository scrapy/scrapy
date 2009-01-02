"""
This module provides some useful functions for working with
scrapy.http.Response objects
"""

from scrapy.http.response import Response

def body_or_str(obj, unicode=True):
    assert isinstance(obj, (Response, basestring)), "obj must be Response or basestring, not %s" % type(obj).__name__
    if isinstance(obj, Response):
        return obj.body.to_unicode() if unicode else obj.body.to_string()
    elif isinstance(obj, str):
        return obj.decode('utf-8') if unicode else obj
    else:
        return obj if unicode else obj.encode('utf-8')
