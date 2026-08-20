.. _websockets:

==========
WebSockets
==========

.. versionadded:: VERSION

.. note:: Requires the :ref:`websockets <extras>` extra and :ref:`asyncio
    support <using-asyncio>`.

A request to a ``ws://`` or ``wss://`` URL performs a WebSocket handshake and
gets a :class:`~scrapy.http.WebSocketResponse`, through which the callback
sends and receives messages over the resulting connection:

.. code-block:: python

    from scrapy import Request, Spider


    class MySpider(Spider):
        name = "quotes"

        async def start(self):
            yield Request("wss://example.com/quotes")

        async def parse(self, response):
            await response.send('{"subscribe": "quotes"}')
            async for message in response:
                yield {"quote": message}

Connection lifetime
===================

A connection stays open until you close it, or until the callback that received
the response is done, whichever happens first. So the spider above keeps
receiving quotes for as long as the server sends them, and a callback that only
needs one reply does not have to close anything.

While the connection is open, its request keeps occupying a downloader slot,
which means that :setting:`CONCURRENT_REQUESTS` and
:setting:`CONCURRENT_REQUESTS_PER_DOMAIN` limit how many connections a spider
can have open at a time. Give a spider that keeps several long-lived
connections open a limit high enough to fit them all, or the remaining requests
never get their turn.

To close a connection earlier than the end of the callback, call
:meth:`~scrapy.http.WebSocketResponse.close`, or use the response as an
asynchronous context manager:

.. code-block:: python

    async def parse(self, response):
        async with response:
            await response.send("hello")
            yield {"reply": await response.receive()}
        yield Request("wss://example.com/other")

Settings and middlewares
========================

A WebSocket handshake is an HTTP request, so it goes through the
:ref:`downloader middlewares <topics-downloader-middleware>` like any other
request: it gets the configured headers, cookies, proxy and :file:`robots.txt`
treatment, and a handshake that the server rejects becomes a regular response
that the redirect and retry middlewares can act on.

:setting:`DOWNLOAD_TIMEOUT` applies to the handshake, and
:setting:`DOWNLOAD_MAXSIZE` to each received message: a message above the limit
closes the connection, making the next :meth:`~scrapy.http.WebSocketResponse.receive`
call raise :exc:`websockets.exceptions.ConnectionClosed`.

.. seealso:: :ref:`websocket-handler`, for the features and limitations of the
    download handler that implements this.

WebSocketResponse objects
=========================

.. autoclass:: scrapy.http.WebSocketResponse
    :members:
