import unittest, json
from cStringIO import StringIO

from scrapy.utils.jsonrpc import jsonrpc_client_call, jsonrpc_server_call, \
    JsonRpcError, jsonrpc_errors
from scrapy.utils.serialize import ScrapyJSONDecoder
from scrapy.tests.test_utils_serialize import CrawlerMock

class urllib_mock(object):
    def __init__(self, result=None, error=None):
        response = {}
        if result:
            response.update(result=result)
        if error:
            response.update(error=error)
        self.response = json.dumps(response)
        self.request = None

    def urlopen(self, url, request):
        self.url = url
        self.request = request
        return StringIO(self.response)

class TestTarget(object):

    def call(self, *args, **kwargs):
        return list(args), kwargs

    def exception(self):
        raise Exception("testing-errors")

class JsonRpcUtilsTestCase(unittest.TestCase):

    def setUp(self):
        crawler = CrawlerMock([])
        self.json_decoder = ScrapyJSONDecoder(crawler=crawler)

    def test_jsonrpc_client_call_args_kwargs_raises(self):
        self.assertRaises(ValueError, jsonrpc_client_call, 'url', 'test', 'one', kw=123)

    def test_jsonrpc_client_call_request(self):
        ul = urllib_mock(1)
        jsonrpc_client_call('url', 'test', 'one', 2, _urllib=ul)
        req = json.loads(ul.request)
        assert 'id' in req
        self.assertEqual(ul.url, 'url')
        self.assertEqual(req['jsonrpc'], '2.0')
        self.assertEqual(req['method'], 'test')
        self.assertEqual(req['params'], ['one', 2])

    def test_jsonrpc_client_call_response(self):
        ul = urllib_mock()
        # must return result or error
        self.assertRaises(ValueError, jsonrpc_client_call, 'url', 'test', _urllib=ul)
        ul = urllib_mock(result={'one': 1})
        self.assertEquals(jsonrpc_client_call('url', 'test', _urllib=ul), {'one': 1})
        ul = urllib_mock(error={'code': 123, 'message': 'hello', 'data': 'some data'})

        raised = False
        try:
            jsonrpc_client_call('url', 'test', _urllib=ul)
        except JsonRpcError as e:
            raised = True
            self.assertEqual(e.code, 123)
            self.assertEqual(e.message, 'hello')
            self.assertEqual(e.data, 'some data')
            assert '123' in str(e)
            assert 'hello' in str(e)
        assert raised, "JsonRpcError not raised"

    def test_jsonrpc_server_call(self):
        t = TestTarget()
        r = jsonrpc_server_call(t, 'invalid json data', self.json_decoder)
        assert 'error' in r
        assert r['jsonrpc'] == '2.0'
        assert r['id'] is None
        self.assertEqual(r['error']['code'], jsonrpc_errors.PARSE_ERROR)
        assert 'Traceback' in r['error']['data']

        r = jsonrpc_server_call(t, '{"test": "test"}', self.json_decoder)
        assert 'error' in r
        assert r['jsonrpc'] == '2.0'
        assert r['id'] is None
        self.assertEqual(r['error']['code'], jsonrpc_errors.INVALID_REQUEST)

        r = jsonrpc_server_call(t, '{"method": "notfound", "id": 1}', self.json_decoder)
        assert 'error' in r
        assert r['jsonrpc'] == '2.0'
        assert r['id'] == 1
        self.assertEqual(r['error']['code'], jsonrpc_errors.METHOD_NOT_FOUND)

        r = jsonrpc_server_call(t, '{"method": "exception", "id": 1}', self.json_decoder)
        assert 'error' in r
        assert r['jsonrpc'] == '2.0'
        assert r['id'] == 1
        self.assertEqual(r['error']['code'], jsonrpc_errors.INTERNAL_ERROR)
        assert 'testing-errors' in r['error']['message']
        assert 'Traceback' in r['error']['data']

        r = jsonrpc_server_call(t, '{"method": "call", "id": 2}', self.json_decoder)
        assert 'result' in r
        assert r['jsonrpc'] == '2.0'
        assert r['id'] == 2
        self.assertEqual(r['result'], ([], {}))

        r = jsonrpc_server_call(t, '{"method": "call", "params": [456, 123], "id": 3}', \
            self.json_decoder)
        assert 'result' in r
        assert r['jsonrpc'] == '2.0'
        assert r['id'] == 3
        self.assertEqual(r['result'], ([456, 123], {}))

        r = jsonrpc_server_call(t, '{"method": "call", "params": {"data": 789}, "id": 3}', \
            self.json_decoder)
        assert 'result' in r
        assert r['jsonrpc'] == '2.0'
        assert r['id'] == 3
        self.assertEqual(r['result'], ([], {'data': 789}))

if __name__ == "__main__":
    unittest.main()

