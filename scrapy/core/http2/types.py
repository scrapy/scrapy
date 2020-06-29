from io import BytesIO
from ipaddress import IPv4Address, IPv6Address
from typing import Union

from twisted.internet.ssl import Certificate
# for python < 3.8 -- typing.TypedDict is undefined
from typing_extensions import TypedDict

from scrapy.http.headers import Headers


class H2ConnectionMetadataDict(TypedDict):
    """Some meta data of this connection
    initialized when connection is successfully made
    """
    certificate: Union[None, Certificate]
    ip_address: Union[None, IPv4Address, IPv6Address]


class H2ResponseDict(TypedDict):
    # Data received frame by frame from the server is appended
    # and passed to the response Deferred when completely received.
    body: BytesIO

    # The amount of data received that counts against the flow control
    # window
    flow_controlled_size: int

    # Headers received after sending the request
    headers: Headers
