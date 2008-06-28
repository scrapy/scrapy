from functools import wraps
from twisted.internet import defer
from scrapy.utils.misc import mustbe_deferred

from .http import HttpResponse


JSONCALLBACK_RE = '^[a-zA-Z][a-zA-Z_.-]*$'
JSON_CONTENT_TYPES = ('application/json',)


def serialize(obj):
    global _serialize
    if not _serialize:
        _loadserializers()
    return _serialize(obj)

def unserialize(obj):
    global _unserialize
    if not _unserialize:
        _loadserializers()
    return _unserialize(obj)


class JsonException(Exception):
    pass

class JsonResponse(HttpResponse):
    def __init__(self, content=None, callback=None, serialize=serialize, *args, **kwargs):
        content = serialize(content)
        if callback: # JSONP support
            status, content = 200, '%s(%s)' % (callback, content)
        kwargs.setdefault('content_type', 'application/x-javascript')
        HttpResponse.__init__(self, content=content, *args, **kwargs)

class JsonResponseAccepted(JsonResponse):
    status_code = 202

class JsonResponseNoContent(JsonResponse):
    status_code = 204

class JsonResponseNotModified(JsonResponse):
    status_code = 304

class JsonResponseBadRequest(JsonResponse):
    status_code = 400

class JsonResponseUnauthorized(JsonResponse):
    status_code = 401

class JsonResponseForbidden(JsonResponse):
    status_code = 403

class JsonResponseNotFound(JsonResponse):
    status_code = 404

class JsonResponseInternalServerError(JsonResponse):
    status_code = 500

class JsonResponseNotImplemented(JsonResponse):
    status_code = 501


def json(func):
    """ Decorator to wrap a json prepared view and return a JsonResponse

    if content-type is application/json, sets request.JSON to unserialized request body.
    in case of unserialization failure, returns JsonResponseBadRequest()

    if returned data from func is a dictionary, serialize it and returns JsonResponse()
    """
    if not hasattr(func, '__call__'):
        raise TypeError('The argument should be a callable')

    @wraps(func)
    def wrapper(request, *args, **kwargs):
        json_callback = request.ARGS.get('callback') # JSONP support
        request.method = method = _x_http_method_override(request)
        request.content_type = ct = content_type(request)
        request.JSON = None

        if method in ('POST', 'PUT'):
            if ct in JSON_CONTENT_TYPES:
                body = request.content.read()
                try:
                    request.JSON = unserialize(body)
                except Exception, e:
                    return JsonResponseBadRequest('Invalid json: %s' % e )

        def _onsuccess(response):
            if not isinstance(response, HttpResponse):
                return JsonResponse(response, json_callback) # best effort
            return response

        ret = mustbe_deferred(func, request, *args, **kwargs)
        ret.addCallback(_onsuccess)
        return ret
    return wrapper

def content_type(request):
    ct = request.HEADERS.get('content-type','')
    return ct.split(';')[0].strip()

def _x_http_method_override(request):
    """ support for X-Http-Method-Override hack

    some clients does not support methods others than GET and POST, that clients
    has a chance to set an extra header to indicate intended method.
    """
    return request.HEADERS.get('x-http-method-override', request.method).upper()


## json serializers

_serialize = _unserialize = None
def _loadserializers():
    global _serialize, _unserialize
    try:
        import cjson
        _serialize = cjson.encode
        _unserialize = cjson.decode
    except ImportError:
        try:
            import simplejson
            _serialize = simplejson.dumps
            _unserialize = simplejson.loads
        except ImportError:
            assert 0, 'json serialization needs cjson or simplejson modules'

