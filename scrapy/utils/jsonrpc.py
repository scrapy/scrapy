"""
This module implements the JSON-RPC 2.0 protocol, as defined in:
http://groups.google.com/group/json-rpc/web/json-rpc-2-0
"""

import urllib
import json
import traceback

from scrapy.utils.serialize import ScrapyJSONDecoder

# JSON-RPC 2.0 errors, as defined in:
class jsonrpc_errors:
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

class JsonRpcError(Exception):

    def __init__(self, code, message, data=None):
        super(JsonRpcError, self).__init__()
        self.code = code
        self.message = message
        self.data = data

    def __str__(self):
        return "JSON-RPC error (code %d): %s" % (self.code, self.message)

def jsonrpc_client_call(url, method, *args, **kwargs):
    """Execute a JSON-RPC call on the given url"""
    _urllib = kwargs.pop('_urllib', urllib)
    if args and kwargs:
        raise ValueError("Pass *args or **kwargs but not both to jsonrpc_client_call")
    req = {'jsonrpc': '2.0', 'method': method, 'params': args or kwargs, 'id': 1}
    res = json.loads(_urllib.urlopen(url, json.dumps(req)).read())
    if 'result' in res:
        return res['result']
    elif 'error' in res:
        er = res['error']
        raise JsonRpcError(er['code'], er['message'], er['data'])
    else:
        msg = "JSON-RPC response must contain 'result' or 'error': %s" % res
        raise ValueError(msg)

def jsonrpc_server_call(target, jsonrpc_request, json_decoder=None):
    """Execute the given JSON-RPC request (as JSON-encoded string) on the given
    target object and return the JSON-RPC response, as a dict
    """
    if json_decoder is None:
        json_decoder = ScrapyJSONDecoder()

    try:
        req = json_decoder.decode(jsonrpc_request)
    except Exception as e:
        return jsonrpc_error(None, jsonrpc_errors.PARSE_ERROR, 'Parse error', \
            traceback.format_exc())

    try:
        id, methname = req['id'], req['method']
    except KeyError:
        return jsonrpc_error(None, jsonrpc_errors.INVALID_REQUEST, 'Invalid Request')

    try:
        method = getattr(target, methname)
    except AttributeError:
        return jsonrpc_error(id, jsonrpc_errors.METHOD_NOT_FOUND, 'Method not found')

    params = req.get('params', [])
    a, kw = ([], params) if isinstance(params, dict) else (params, {})
    kw = dict([(str(k), v) for k, v in kw.items()]) # convert kw keys to str
    try:
        return jsonrpc_result(id, method(*a, **kw))
    except Exception as e:
        return jsonrpc_error(id, jsonrpc_errors.INTERNAL_ERROR, str(e), \
            traceback.format_exc())

def jsonrpc_error(id, code, message, data=None):
    """Create JSON-RPC error response"""
    return {
        'jsonrpc': '2.0',
        'error': {
            'code': code,
            'message': message,
            'data': data,
        },
        'id': id,
    }

def jsonrpc_result(id, result):
    """Create JSON-RPC result response"""
    return {
        'jsonrpc': '2.0',
        'result': result,
        'id': id,
    }
