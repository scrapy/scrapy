"""
Helper functions for serializing (and deserializing) requests.
"""
import inspect

from scrapy.http import Request
from scrapy.utils.python import to_unicode
from scrapy.utils.misc import load_object


def request_to_dict(request, spider=None):
    """Convert Request object to a dict.

    If a spider is given, it will try to find out the name of the spider method
    used in the callback and store that as the callback.
    """
    cb = request.callback
    if callable(cb):
        cb = _find_method(spider, cb)
    eb = request.errback
    if callable(eb):
        eb = _find_method(spider, eb)
    d = {
        'url': to_unicode(request.url),  # urls should be safe (safe_string_url)
        'callback': cb,
        'errback': eb,
        'method': request.method,
        'headers': dict(request.headers),
        'body': request.body,
        'cookies': request.cookies,
        'meta': request.meta,
        '_encoding': request._encoding,
        'priority': request.priority,
        'dont_filter': request.dont_filter,
        'flags': request.flags,
        'cb_kwargs': request.cb_kwargs,
    }
    if type(request) is not Request:
        d['_class'] = request.__module__ + '.' + request.__class__.__name__
    return d


def request_from_dict(d, spider=None):
    """Create Request object from a dict.

    If a spider is given, it will try to resolve the callbacks looking at the
    spider for methods with the same name.
    """
    cb = d['callback']
    if cb and spider:
        cb = _get_method(spider, cb)
    eb = d['errback']
    if eb and spider:
        eb = _get_method(spider, eb)
    request_cls = load_object(d['_class']) if '_class' in d else Request
    return request_cls(
        url=to_unicode(d['url']),
        callback=cb,
        errback=eb,
        method=d['method'],
        headers=d['headers'],
        body=d['body'],
        cookies=d['cookies'],
        meta=d['meta'],
        encoding=d['_encoding'],
        priority=d['priority'],
        dont_filter=d['dont_filter'],
        flags=d.get('flags'),
        cb_kwargs=d.get('cb_kwargs'),
    )


def _find_method(obj, func):
    if obj:
        try:
            func_self = func.__self__
        except AttributeError:  # func has no __self__
            pass
        else:
            if func_self is obj:
                members = inspect.getmembers(obj, predicate=inspect.ismethod)
                for name, obj_func in members:
                    # We need to use __func__ to access the original
                    # function object because instance method objects
                    # are generated each time attribute is retrieved from
                    # instance.
                    #
                    # Reference: The standard type hierarchy
                    # https://docs.python.org/3/reference/datamodel.html
                    if obj_func.__func__ is func.__func__:
                        return name
    raise ValueError("Function %s is not a method of: %s" % (func, obj))


def _get_method(obj, name):
    name = str(name)
    try:
        return getattr(obj, name)
    except AttributeError:
        raise ValueError("Method %r not found in: %s" % (name, obj))
