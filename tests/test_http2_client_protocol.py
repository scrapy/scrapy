# TODO: Add test cases for
#   1. No Content Length response header
#   2. Cancel Response Deferred
import json
import os
import random
import shutil
import string

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, DeferredList
from twisted.internet.endpoints import SSL4ClientEndpoint, SSL4ServerEndpoint, TCP4ServerEndpoint
from twisted.internet.protocol import Factory
from twisted.internet.ssl import optionsForClientTLS, PrivateCertificate
from twisted.trial.unittest import TestCase
from twisted.web.http import Request as TxRequest
from twisted.web.resource import Resource
from twisted.web.server import Site
from twisted.web.static import File

from scrapy.core.http2.protocol import H2ClientProtocol
from scrapy.http import Request, Response, JsonRequest
from tests.mockserver import ssl_context_factory


def generate_random_string(size):
    return ''.join(random.choices(
        string.ascii_uppercase + string.digits,
        k=size
    ))


def make_html_body(val):
    response = '''<html>
<h1>Hello from HTTP2<h1>
<p>{}</p>
</html>'''.format(val)
    return bytes(response, 'utf-8')


class Data:
    SMALL_SIZE = 1024 * 10  # 10 KB
    LARGE_SIZE = (1024 ** 2) * 10  # 10 MB

    STR_SMALL = generate_random_string(SMALL_SIZE)
    STR_LARGE = generate_random_string(LARGE_SIZE)

    EXTRA_SMALL = generate_random_string(1024 * 15)
    EXTRA_LARGE = generate_random_string((1024 ** 2) * 15)

    HTML_SMALL = make_html_body(STR_SMALL)
    HTML_LARGE = make_html_body(STR_LARGE)

    JSON_SMALL = {'data': STR_SMALL}
    JSON_LARGE = {'data': STR_LARGE}


class LeafResource(Resource):
    isLeaf = True


class GetDataHtmlSmall(LeafResource):
    def render_GET(self, request: TxRequest):
        request.setHeader('Content-Type', 'text/html; charset=UTF-8')
        return Data.HTML_SMALL


class GetDataHtmlLarge(LeafResource):
    def render_GET(self, request: TxRequest):
        request.setHeader('Content-Type', 'text/html; charset=UTF-8')
        return Data.HTML_LARGE


class PostDataJsonMixin:
    @staticmethod
    def make_response(request: TxRequest, extra_data: str):
        response = {
            'request-headers': {},
            'request-body': json.loads(request.content.read()),
            'extra-data': extra_data
        }
        for k, v in request.requestHeaders.getAllRawHeaders():
            response['request-headers'][k.decode('utf-8')] = v[0].decode('utf-8')

        response_bytes = bytes(json.dumps(response), 'utf-8')
        request.setHeader('Content-Type', 'application/json')
        return response_bytes


class PostDataJsonSmall(LeafResource, PostDataJsonMixin):
    def render_POST(self, request: TxRequest):
        return self.make_response(request, Data.EXTRA_SMALL)


class PostDataJsonLarge(LeafResource, PostDataJsonMixin):
    def render_POST(self, request: TxRequest):
        return self.make_response(request, Data.EXTRA_LARGE)


def get_client_certificate(key_file, certificate_file):
    with open(key_file, 'r') as key, open(certificate_file, 'r') as certificate:
        pem = ''.join(key.readlines()) + ''.join(certificate.readlines())

    return PrivateCertificate.loadPEM(pem)


class Https2ClientProtocolTestCase(TestCase):
    scheme = 'https'
    key_file = os.path.join(os.path.dirname(__file__), 'keys', 'localhost.key')
    certificate_file = os.path.join(os.path.dirname(__file__), 'keys', 'localhost.crt')

    def _init_resource(self):
        self.temp_directory = self.mktemp()
        os.mkdir(self.temp_directory)
        r = File(self.temp_directory)
        r.putChild(b'get-data-html-small', GetDataHtmlSmall())
        r.putChild(b'get-data-html-large', GetDataHtmlLarge())

        r.putChild(b'post-data-json-small', PostDataJsonSmall())
        r.putChild(b'post-data-json-large', PostDataJsonLarge())
        return r

    @inlineCallbacks
    def setUp(self):
        # Initialize resource tree
        root = self._init_resource()
        self.site = Site(root, timeout=None)

        # Start server for testing
        self.hostname = u'localhost'
        if self.scheme == 'https':
            context_factory = ssl_context_factory(self.key_file, self.certificate_file)
            server_endpoint = SSL4ServerEndpoint(reactor, 0, context_factory, interface=self.hostname)
        else:
            server_endpoint = TCP4ServerEndpoint(reactor, 0, interface=self.hostname)
        self.server = yield server_endpoint.listen(self.site)
        self.port_number = self.server.getHost().port

        # Connect H2 client with server
        client_certificate = get_client_certificate(self.key_file, self.certificate_file)
        client_options = optionsForClientTLS(
            hostname=self.hostname,
            trustRoot=client_certificate,
            acceptableProtocols=[b'h2']
        )
        h2_client_factory = Factory.forProtocol(H2ClientProtocol)
        client_endpoint = SSL4ClientEndpoint(reactor, self.hostname, self.port_number, client_options)
        self.client = yield client_endpoint.connect(h2_client_factory)

    @inlineCallbacks
    def tearDown(self):
        yield self.client.transport.loseConnection()
        yield self.client.transport.abortConnection()
        yield self.server.stopListening()
        shutil.rmtree(self.temp_directory)

    def get_url(self, path):
        """
        :param path: Should have / at the starting compulsorily if not empty
        :return: Complete url
        """
        assert len(path) > 0 and (path[0] == '/' or path[0] == '&')
        return "{}://{}:{}{}".format(self.scheme, self.hostname, self.port_number, path)

    @staticmethod
    def _check_repeat(get_deferred, count):
        d_list = []
        for _ in range(count):
            d = get_deferred()
            d_list.append(d)

        return DeferredList(d_list, fireOnOneErrback=True)

    def _check_GET(
            self,
            request: Request,
            expected_body,
            expected_status
    ):
        def check_response(response: Response):
            self.assertEqual(response.status, expected_status)
            self.assertEqual(response.body, expected_body)
            self.assertEqual(response.request, request)
            self.assertEqual(response.url, request.url)

            content_length = int(response.headers.get('Content-Length'))
            self.assertEqual(len(response.body), content_length)

        d = self.client.request(request)
        d.addCallback(check_response)
        d.addErrback(self.fail)
        return d

    def test_GET_small_body(self):
        request = Request(self.get_url('/get-data-html-small'))
        return self._check_GET(request, Data.HTML_SMALL, 200)

    def test_GET_large_body(self):
        request = Request(self.get_url('/get-data-html-large'))
        return self._check_GET(request, Data.HTML_LARGE, 200)

    def _check_GET_x20(self, *args, **kwargs):
        def get_deferred():
            return self._check_GET(*args, **kwargs)

        return self._check_repeat(get_deferred, 20)

    def test_GET_small_body_x20(self):
        return self._check_GET_x20(
            Request(self.get_url('/get-data-html-small')),
            Data.HTML_SMALL,
            200
        )

    def test_GET_large_body_x20(self):
        return self._check_GET_x20(
            Request(self.get_url('/get-data-html-large')),
            Data.HTML_LARGE,
            200
        )

    def _check_POST_json(
            self,
            request: Request,
            expected_request_body,
            expected_extra_data,
            expected_status: int
    ):
        d = self.client.request(request)

        def assert_response(response: Response):
            self.assertEqual(response.status, expected_status)
            self.assertEqual(response.request, request)
            self.assertEqual(response.url, request.url)

            content_length = int(response.headers.get('Content-Length'))
            self.assertEqual(len(response.body), content_length)

            # Parse the body
            body = json.loads(response.body.decode('utf-8'))
            self.assertIn('request-body', body)
            self.assertIn('extra-data', body)
            self.assertIn('request-headers', body)

            request_body = body['request-body']
            self.assertEqual(request_body, expected_request_body)

            extra_data = body['extra-data']
            self.assertEqual(extra_data, expected_extra_data)

            # Check if headers were sent successfully
            request_headers = body['request-headers']
            for k, v in request.headers.items():
                k_str = k.decode('utf-8')
                self.assertIn(k_str, request_headers)
                self.assertEqual(request_headers[k_str], v[0].decode('utf-8'))

        d.addCallback(assert_response)
        return d

    def test_POST_small_json(self):
        request = JsonRequest(url=self.get_url('/post-data-json-small'), method='POST', data=Data.JSON_SMALL)
        return self._check_POST_json(
            request,
            Data.JSON_SMALL,
            Data.EXTRA_SMALL,
            200
        )

    def test_POST_large_json(self):
        request = JsonRequest(url=self.get_url('/post-data-json-large'), method='POST', data=Data.JSON_LARGE)
        return self._check_POST_json(
            request,
            Data.JSON_LARGE,
            Data.EXTRA_LARGE,
            200
        )

    def _check_POST_json_x20(self, *args, **kwargs):
        def get_deferred():
            return self._check_POST_json(*args, **kwargs)

        return self._check_repeat(get_deferred, 20)

    def test_POST_small_json_x20(self):
        request = JsonRequest(url=self.get_url('/post-data-json-small'), method='POST', data=Data.JSON_SMALL)
        return self._check_POST_json_x20(
            request,
            Data.JSON_SMALL,
            Data.EXTRA_SMALL,
            200
        )

    def test_POST_large_json_x20(self):
        request = JsonRequest(url=self.get_url('/post-data-json-large'), method='POST', data=Data.JSON_LARGE)
        return self._check_POST_json_x20(
            request,
            Data.JSON_LARGE,
            Data.EXTRA_LARGE,
            200
        )

    def test_cancel_request(self):
        request = Request(url=self.get_url('/get-data-html-large'))

        def assert_response(response: Response):
            self.assertEqual(response.status, 499)
            self.assertEqual(response.request, request)
            self.assertEqual(response.url, request.url)

        d = self.client.request(request)
        d.addCallback(assert_response)
        d.cancel()

        return d
