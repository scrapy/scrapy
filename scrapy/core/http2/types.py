from io import BytesIO
from ipaddress import IPv4Address, IPv6Address
from typing import Union, Optional

from twisted.internet.ssl import Certificate
# for python < 3.8 -- typing.TypedDict is undefined
from typing_extensions import TypedDict

from scrapy.http.headers import Headers


class H2ConnectionMetadataDict(TypedDict):
    """Some meta data of this connection
    initialized when connection is successfully made
    """
    certificate: Optional[Certificate]

    # Address of the server we are connected to which
    # is updated when HTTP/2 connection is  made successfully
    ip_address: Optional[Union[IPv4Address, IPv6Address]]

    # Name of the peer HTTP/2 connection is established
    hostname: Optional[str]

    port: Optional[int]

    # Both ip_address and hostname are used by the Stream before
    # initiating the request to verify that the base address


class H2ResponseDict(TypedDict):
    # Data received frame by frame from the server is appended
    # and passed to the response Deferred when completely received.
    body: BytesIO

    # The amount of data received that counts against the flow control
    # window
    flow_controlled_size: int

    # Headers received after sending the request
    headers: Headers
