# This is simple script to test

import json

from twisted.internet import reactor
from twisted.internet.endpoints import connectProtocol, SSL4ClientEndpoint
from twisted.internet.ssl import optionsForClientTLS

from scrapy.core.http2.protocol import H2ClientProtocol
from scrapy.http import Request, Response, JsonRequest

try:
    with open('data.json', 'r') as f:
        JSON_DATA = json.load(f)
except:
    JSON_DATA = {
        "data": "To test for really large amount of data -- Add data.json with lots of data.",
        "why": "To test whether correct data is sent :)"
    }

# Use nghttp2 for testing whether basic setup works - for small response
HTTPBIN_AUTHORITY = u'nghttp2.org'
HTTPBIN_REQUEST_URLS = 1 * [
    Request(url='https://nghttp2.org/httpbin/get', method='GET'),
    Request(url='https://nghttp2.org/httpbin/post', method='POST'),
    JsonRequest(url='https://nghttp2.org/httpbin/anything', method='POST', data=JSON_DATA),
]

# Use POKE_API for testing large responses
POKE_API_AUTHORITY = u'pokeapi.co'
POKE_API_REQUESTS = 15 * [
    Request(url='https://pokeapi.co/api/v2/pokemon/ditto', method='GET'),
    Request(url='https://pokeapi.co/api/v2/pokemon/charizard', method='GET'),
    Request(url='https://pokeapi.co/api/v2/pokemon/pikachu', method='GET'),
    Request(url='https://pokeapi.co/api/v2/pokemon/DoesNotExist', method='GET'),  # should give 404
]

AUTHORITY = POKE_API_AUTHORITY
REQUEST_URLS = POKE_API_REQUESTS

options = optionsForClientTLS(
    hostname=AUTHORITY,
    acceptableProtocols=[b'h2'],
)

protocol = H2ClientProtocol()

count_responses = 1


def print_response(response):
    global count_responses
    assert isinstance(response, Response)
    print('({})\t{}: ReponseBodySize={}'.format(count_responses, response, len(response.body)))
    count_responses = count_responses + 1


for request in REQUEST_URLS:
    d = protocol.request(request)
    d.addCallback(print_response)

connectProtocol(
    SSL4ClientEndpoint(reactor, AUTHORITY, 443, options),
    protocol
)

reactor.run()
