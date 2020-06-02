from scrapy.http.headers import Headers


class Stream:
    """Represents a single HTTP/2 Stream.

    Stream is a bidirectional flow of bytes within an established connection,
    which may carry one or more messages. Handles the tranfer of HTTP Headers
    and Data frames.
    """

    def __init__(self, stream_id, headers):
        """
        Arguments:
            stream_id {int} -- For one HTTP/2 connection each stream is
                uniquely identified by a single integer
            headers {Headers} -- HTTP request headers
        """

        # Headers received after sending the request
        self.response_headers = Headers({})

        # Headers which are send with the request
        # These cannot be modified any furthur
        self._request_headers = headers

        # TODO: Add canceller for the Deferred below
        self._deferred_response = Deferred()

    def get_response(self):
        """Simply return a Deferred which fires when response
        from the asynchronous request is available

        Returns:
            Deferred -- Calls the callback when the response is
                avaialble
        """
        return self._deferred_response

    def receive_data(self, data):
        pass

    def receive_headers(self, headers):
        pass
