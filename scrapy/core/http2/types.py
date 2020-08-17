from io import BytesIO
from ipaddress import IPv4Address, IPv6Address
from typing import Union, Optional

from twisted.internet.ssl import Certificate
from twisted.web.client import URI
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

    # URI of the peer HTTP/2 connection is made
    uri: URI

    # Both ip_address and uri are used by the Stream before
    # initiating the request to verify that the base address

    # Variables taken from Project Settings
    default_download_maxsize: int
    default_download_warnsize: int


class H2StreamMetadataDict(TypedDict):
    """Metadata of an HTTP/2 connection stream
    initialized when stream is instantiated
    """

    request_content_length: int

    # Flag to keep track whether the stream has initiated the request
    request_sent: bool

    # Flag to track whether we have logged about exceeding download warnsize
    reached_warnsize: bool

    # Each time we send a data frame, we will decrease value by the amount send.
    remaining_content_length: int

    # Flag to keep track whether we have closed this stream
    stream_closed_local: bool

    # Flag to keep track whether the server has closed the stream
    stream_closed_server: bool


class H2ResponseDict(TypedDict):
    # Data received frame by frame from the server is appended
    # and passed to the response Deferred when completely received.
    body: BytesIO

    # The amount of data received that counts against the flow control
    # window
    flow_controlled_size: int

    # Headers received after sending the request
    headers: Headers
