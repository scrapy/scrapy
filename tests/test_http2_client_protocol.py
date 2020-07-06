import json
import os
import random
import re
import shutil
import string
from ipaddress import IPv4Address
from urllib.parse import urlencode

from h2.exceptions import InvalidBodyLengthError
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, DeferredList, CancelledError
from twisted.internet.endpoints import SSL4ClientEndpoint, SSL4ServerEndpoint
from twisted.internet.protocol import Factory
from twisted.internet.ssl import optionsForClientTLS, PrivateCertificate, Certificate
from twisted.python.failure import Failure
from twisted.trial.unittest import TestCase
from twisted.web.http import Request as TxRequest
from twisted.web.server import Site, NOT_DONE_YET
from twisted.web.static import File

from scrapy.core.http2.protocol import H2ClientProtocol
from scrapy.core.http2.stream import InactiveStreamClosed, InvalidHostname
from scrapy.http import Request, Response, JsonRequest
from scrapy.utils.python import to_bytes, to_unicode
from tests.mockserver import ssl_context_factory, LeafResource, Status


def generate_random_string(size):
    return ''.join(random.choices(
        string.ascii_uppercase + string.digits,
        k=size
    ))


def make_html_body(val):
    response = f'''<html>
<h1>Hello from HTTP2<h1>
<p>{val}</p>
</html>'''
    return to_bytes(response)


class Data:
    SMALL_SIZE = 1024  # 1 KB
    LARGE_SIZE = 1024 ** 2  # 1 MB

    STR_SMALL = generate_random_string(SMALL_SIZE)
    STR_LARGE = generate_random_string(LARGE_SIZE)

    EXTRA_SMALL = generate_random_string(1024 * 15)
    EXTRA_LARGE = generate_random_string((1024 ** 2) * 15)

    HTML_SMALL = make_html_body(STR_SMALL)
    HTML_LARGE = make_html_body(STR_LARGE)

    JSON_SMALL = {'data': STR_SMALL}
    JSON_LARGE = {'data': STR_LARGE}

    DATALOSS = b'Dataloss Content'
    NO_CONTENT_LENGTH = b'This response do not have any content-length header'


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
            response['request-headers'][to_unicode(k)] = to_unicode(v[0])

        response_bytes = to_bytes(json.dumps(response))
        request.setHeader('Content-Type', 'application/json')
        return response_bytes


class PostDataJsonSmall(LeafResource, PostDataJsonMixin):
    def render_POST(self, request: TxRequest):
        return self.make_response(request, Data.EXTRA_SMALL)


class PostDataJsonLarge(LeafResource, PostDataJsonMixin):
    def render_POST(self, request: TxRequest):
        return self.make_response(request, Data.EXTRA_LARGE)


class Dataloss(LeafResource):

    def render_GET(self, request: TxRequest):
        request.setHeader(b"Content-Length", b"1024")
        self.deferRequest(request, 0, self._delayed_render, request)
        return NOT_DONE_YET

    @staticmethod
    def _delayed_render(request: TxRequest):
        request.write(Data.DATALOSS)
        request.finish()


class NoContentLengthHeader(LeafResource):
    def render_GET(self, request: TxRequest):
        request.requestHeaders.removeHeader('Content-Length')
        self.deferRequest(request, 0, self._delayed_render, request)
        return NOT_DONE_YET

    @staticmethod
    def _delayed_render(request: TxRequest):
        request.write(Data.NO_CONTENT_LENGTH)
        request.finish()


class QueryParams(LeafResource):
    def render_GET(self, request: TxRequest):
        request.setHeader('Content-Type', 'application/json')

        query_params = {}
        for k, v in request.args.items():
            query_params[to_unicode(k)] = to_unicode(v[0])

        return to_bytes(json.dumps(query_params))


def get_client_certificate(key_file, certificate_file) -> PrivateCertificate:
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

        r.putChild(b'dataloss', Dataloss())
        r.putChild(b'no-content-length-header', NoContentLengthHeader())
        r.putChild(b'status', Status())
        r.putChild(b'query-params', QueryParams())
        return r

    @inlineCallbacks
    def setUp(self):
        # Initialize resource tree
        root = self._init_resource()
        self.site = Site(root, timeout=None)

        # Start server for testing
        self.hostname = u'localhost'
        context_factory = ssl_context_factory(self.key_file, self.certificate_file)
        server_endpoint = SSL4ServerEndpoint(reactor, 0, context_factory, interface=self.hostname)
        self.server = yield server_endpoint.listen(self.site)
        self.port_number = self.server.getHost().port

        # Connect H2 client with server
        self.client_certificate = get_client_certificate(self.key_file, self.certificate_file)
        client_options = optionsForClientTLS(
            hostname=self.hostname,
            trustRoot=self.client_certificate,
            acceptableProtocols=[b'h2']
        )
        h2_client_factory = Factory.forProtocol(H2ClientProtocol)
        client_endpoint = SSL4ClientEndpoint(reactor, self.hostname, self.port_number, client_options)
        self.client = yield client_endpoint.connect(h2_client_factory)

    @inlineCallbacks
    def tearDown(self):
        if self.client.is_connected:
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
        return f'{self.scheme}://{self.hostname}:{self.port_number}{path}'

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

    def _check_GET_x10(self, *args, **kwargs):
        def get_deferred():
            return self._check_GET(*args, **kwargs)

        return self._check_repeat(get_deferred, 10)

    def test_GET_small_body_x10(self):
        return self._check_GET_x10(
            Request(self.get_url('/get-data-html-small')),
            Data.HTML_SMALL,
            200
        )

    def test_GET_large_body_x10(self):
        return self._check_GET_x10(
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

            content_length = int(response.headers.get('Content-Length'))
            self.assertEqual(len(response.body), content_length)

            # Parse the body
            body = json.loads(to_unicode(response.body))
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
                k_str = to_unicode(k)
                self.assertIn(k_str, request_headers)
                self.assertEqual(request_headers[k_str], to_unicode(v[0]))

        d.addCallback(assert_response)
        d.addErrback(self.fail)
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

    def _check_POST_json_x10(self, *args, **kwargs):
        def get_deferred():
            return self._check_POST_json(*args, **kwargs)

        return self._check_repeat(get_deferred, 10)

    def test_POST_small_json_x10(self):
        request = JsonRequest(url=self.get_url('/post-data-json-small'), method='POST', data=Data.JSON_SMALL)
        return self._check_POST_json_x10(
            request,
            Data.JSON_SMALL,
            Data.EXTRA_SMALL,
            200
        )

    def test_POST_large_json_x10(self):
        request = JsonRequest(url=self.get_url('/post-data-json-large'), method='POST', data=Data.JSON_LARGE)
        return self._check_POST_json_x10(
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

        d = self.client.request(request)
        d.addCallback(assert_response)
        d.addErrback(self.fail)
        d.cancel()

        return d

    def test_download_maxsize_exceeded(self):
        request = Request(url=self.get_url('/get-data-html-large'), meta={'download_maxsize': 1000})

        def assert_cancelled_error(failure):
            self.assertIsInstance(failure.value, CancelledError)

        d = self.client.request(request)
        d.addCallback(self.fail)
        d.addErrback(assert_cancelled_error)
        return d

    def test_received_dataloss_response(self):
        """In case when value of Header Content-Length != len(Received Data)
        ProtocolError is raised"""
        request = Request(url=self.get_url('/dataloss'))

        def assert_failure(failure: Failure):
            self.assertTrue(len(failure.value.reasons) > 0)
            self.assertTrue(any(
                isinstance(error, InvalidBodyLengthError)
                for error in failure.value.reasons
            ))

        d = self.client.request(request)
        d.addCallback(self.fail)
        d.addErrback(assert_failure)
        return d

    def test_missing_content_length_header(self):
        request = Request(url=self.get_url('/no-content-length-header'))

        def assert_content_length(response: Response):
            self.assertEqual(response.status, 200)
            self.assertEqual(response.body, Data.NO_CONTENT_LENGTH)
            self.assertEqual(response.request, request)
            self.assertIn('partial', response.flags)
            self.assertNotIn('Content-Length', response.headers)

        d = self.client.request(request)
        d.addCallback(assert_content_length)
        d.addErrback(self.fail)
        return d

    @inlineCallbacks
    def _check_log_warnsize(
        self,
        request,
        warn_pattern,
        expected_body
    ):
        with self.assertLogs('scrapy.core.http2.stream', level='WARNING') as cm:
            response = yield self.client.request(request)
            self.assertEqual(response.status, 200)
            self.assertEqual(response.request, request)
            self.assertEqual(response.body, expected_body)

            # Check the warning is raised only once for this request
            self.assertEqual(sum(
                len(re.findall(warn_pattern, log))
                for log in cm.output
            ), 1)

    @inlineCallbacks
    def test_log_expected_warnsize(self):
        request = Request(url=self.get_url('/get-data-html-large'), meta={'download_warnsize': 1000})
        warn_pattern = re.compile(
            rf'Expected response size \(\d*\) larger than '
            rf'download warn size \(1000\) in request {request}'
        )

        yield self._check_log_warnsize(request, warn_pattern, Data.HTML_LARGE)

    @inlineCallbacks
    def test_log_received_warnsize(self):
        request = Request(url=self.get_url('/no-content-length-header'), meta={'download_warnsize': 10})
        warn_pattern = re.compile(
            rf'Received more \(\d*\) bytes than download '
            rf'warn size \(10\) in request {request}'
        )

        yield self._check_log_warnsize(request, warn_pattern, Data.NO_CONTENT_LENGTH)

    def test_max_concurrent_streams(self):
        """Send 500 requests at one to check if we can handle
        very large number of request.
        """

        def get_deferred():
            return self._check_GET(
                Request(self.get_url('/get-data-html-small')),
                Data.HTML_SMALL,
                200
            )

        return self._check_repeat(get_deferred, 500)

    def test_inactive_stream(self):
        """Here we send 110 requests considering the MAX_CONCURRENT_STREAMS
        by default is 100. After sending the first 100 requests we close the
        connection."""
        d_list = []

        def assert_inactive_stream(failure):
            self.assertIsNotNone(failure.check(InactiveStreamClosed))

        # Send 100 request (we do not check the result)
        for _ in range(100):
            d = self.client.request(Request(self.get_url('/get-data-html-small')))
            d.addBoth(lambda _: None)
            d_list.append(d)

        # Now send 10 extra request and save the response deferred in a list
        for _ in range(10):
            d = self.client.request(Request(self.get_url('/get-data-html-small')))
            d.addCallback(self.fail)
            d.addErrback(assert_inactive_stream)
            d_list.append(d)

        # Close the connection now to fire all the extra 10 requests errback
        # with InactiveStreamClosed
        self.client.transport.loseConnection()

        return DeferredList(d_list, consumeErrors=True, fireOnOneErrback=True)

    def test_invalid_request_type(self):
        with self.assertRaises(TypeError):
            self.client.request('https://InvalidDataTypePassed.com')

    def test_query_parameters(self):
        params = {
            'a': generate_random_string(20),
            'b': generate_random_string(20),
            'c': generate_random_string(20),
            'd': generate_random_string(20)
        }
        request = Request(self.get_url(f'/query-params?{urlencode(params)}'))

        def assert_query_params(response: Response):
            data = json.loads(to_unicode(response.body))
            self.assertEqual(data, params)

        d = self.client.request(request)
        d.addCallback(assert_query_params)
        d.addErrback(self.fail)

        return d

    def test_status_codes(self):
        def assert_response_status(response: Response, expected_status: int):
            self.assertEqual(response.status, expected_status)

        d_list = []
        for status in [200, 404]:
            request = Request(self.get_url(f'/status?n={status}'))
            d = self.client.request(request)
            d.addCallback(assert_response_status, status)
            d.addErrback(self.fail)
            d_list.append(d)

        return DeferredList(d_list, fireOnOneErrback=True)

    def test_response_has_correct_certificate_ip_address(self):
        request = Request(self.get_url('/status?n=200'))

        def assert_metadata(response: Response):
            self.assertEqual(response.request, request)
            self.assertIsInstance(response.certificate, Certificate)
            self.assertIsNotNone(response.certificate.original)
            self.assertEqual(response.certificate.getIssuer(), self.client_certificate.getIssuer())
            self.assertTrue(response.certificate.getPublicKey().matches(self.client_certificate.getPublicKey()))

            self.assertIsInstance(response.ip_address, IPv4Address)
            self.assertEqual(str(response.ip_address), '127.0.0.1')

        d = self.client.request(request)
        d.addCallback(assert_metadata)
        d.addErrback(self.fail)

        return d

    def _check_invalid_netloc(self, url):
        request = Request(url)

        def assert_invalid_hostname(failure: Failure):
            self.assertIsNotNone(failure.check(InvalidHostname))
            error_msg = str(failure.value)
            self.assertIn('localhost', error_msg)
            self.assertIn('127.0.0.1', error_msg)
            self.assertIn(str(request), error_msg)

        d = self.client.request(request)
        d.addCallback(self.fail)
        d.addErrback(assert_invalid_hostname)
        return d

    def test_invalid_hostname(self):
        return self._check_invalid_netloc('https://notlocalhost.notlocalhostdomain')

    def test_invalid_host_port(self):
        port = self.port_number + 1
        return self._check_invalid_netloc(f'https://127.0.0.1:{port}')

    def test_connection_stays_with_invalid_requests(self):
        d_list = [
            self.test_invalid_hostname(),
            self.test_invalid_host_port(),
            self.test_GET_small_body(),
            self.test_POST_small_json()
        ]

        return DeferredList(d_list, fireOnOneErrback=True)
