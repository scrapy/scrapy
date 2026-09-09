.. _cookies:
.. _cookies-mw:

=======
Cookies
=======

Scrapy keeps track of the cookies that websites set and sends them back on
later requests to those websites, just like a web browser does. That is the job
of :class:`~scrapy.downloadermiddlewares.cookies.CookiesMiddleware`, which is
enabled by default.


Setting cookies on a request
============================

.. invisible-code-block: python

    from scrapy import Request

Use the ``cookies`` parameter of :class:`~scrapy.Request` to send cookies of
your own, either as a dict:

.. code-block:: python

    request = Request(
        url="https://example.com",
        cookies={"currency": "USD", "country": "UY"},
    )

Or as a list of dicts, which also lets you set cookie attributes:

.. code-block:: python

    request = Request(
        url="https://example.com",
        cookies=[
            {
                "name": "currency",
                "value": "USD",
                "domain": "example.com",
                "path": "/currency",
                "secure": True,
            },
        ],
    )

Setting attributes is only useful if the cookies are stored for later requests,
i.e. if :reqmeta:`dont_merge_cookies` is not enabled.

.. caution:: Cookies set through the ``Cookie`` header are not handled by
    :class:`~scrapy.downloadermiddlewares.cookies.CookiesMiddleware`, which
    drops that header.

.. caution:: When a cookie name or value is a byte sequence that is not UTF-8
    encoded, the cookie is dropped and a warning is logged. See
    :ref:`topics-logging-advanced-customization` to customize the logging
    behavior.


.. reqmeta:: cookiejar

Multiple cookie sessions per spider
===================================

By default all requests share a single cookie jar (session). To use different
ones, pass an identifier in the :reqmeta:`cookiejar` request meta key:

.. skip: next
.. code-block:: python

    for i, url in enumerate(urls):
        yield Request(url, meta={"cookiejar": i}, callback=self.parse_page)

The :reqmeta:`cookiejar` meta key is not "sticky", so you need to keep passing
it along on subsequent requests:

.. code-block:: python

    def parse_page(self, response):
        return Request(
            "https://example.com/otherpage",
            meta={"cookiejar": response.meta["cookiejar"]},
            callback=self.parse_other_page,
        )


.. reqmeta:: dont_merge_cookies

Skipping the cookie jar for a request
=====================================

Set the :reqmeta:`dont_merge_cookies` request meta key to ``True`` to keep a
request from touching the cookie jar in either direction: no stored cookie is
sent with the request, and no cookie received in the response is stored. The
cookies of the request itself are ignored as well.


.. setting:: COOKIES_ENABLED

COOKIES_ENABLED
===============

Default: ``True``

Whether to enable :class:`~scrapy.downloadermiddlewares.cookies.CookiesMiddleware`.
If disabled, no cookies are sent to web servers.


.. setting:: COOKIES_DEBUG

COOKIES_DEBUG
=============

Default: ``False``

If enabled, Scrapy logs all cookies sent in requests (i.e. the ``Cookie``
header) and all cookies received in responses (i.e. the ``Set-Cookie``
header)::

    2011-04-06 14:35:10-0300 [scrapy.core.engine] INFO: Spider opened
    2011-04-06 14:35:10-0300 [scrapy.downloadermiddlewares.cookies] DEBUG: Sending cookies to: <GET http://www.diningcity.com/netherlands/index.html>
            Cookie: clientlanguage_nl=en_EN
    2011-04-06 14:35:14-0300 [scrapy.downloadermiddlewares.cookies] DEBUG: Received cookies from: <200 http://www.diningcity.com/netherlands/index.html>
            Set-Cookie: JSESSIONID=B~FA4DC0C496C8762AE4F1A620EAB34F38; Path=/
            Set-Cookie: ip_isocode=US
            Set-Cookie: clientlanguage_nl=en_EN; Expires=Thu, 07-Apr-2011 21:21:34 GMT; Path=/
    2011-04-06 14:49:50-0300 [scrapy.core.engine] DEBUG: Crawled (200) <GET http://www.diningcity.com/netherlands/index.html> (referer: None)
    [...]


CookiesMiddleware
=================

.. module:: scrapy.downloadermiddlewares.cookies
   :synopsis: Cookies Downloader Middleware

.. autoclass:: CookiesMiddleware
