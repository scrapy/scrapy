.. _sessions:
.. _cookies:
.. _cookies-mw:

========
Sessions
========

A session is the state that a group of requests share, starting with their
cookies, which Scrapy stores and sends back on later requests to the same
website, like a web browser does.

Every request uses the same session unless told otherwise, so a crawl behaves
like a single browser profile. Use more than one to keep parts of a crawl from
sharing state, e.g. to crawl a website through several independent profiles at
the same time.


.. _session-choose:

Choosing the session of a request
=================================

.. versionadded:: VERSION

.. invisible-code-block: python

    from scrapy import Request

.. reqmeta:: session

Set the :reqmeta:`session` request meta key to a session ID:

.. skip: next
.. code-block:: python

    for index, url in enumerate(urls):
        yield Request(url, meta={"session": index})

Any ID works, and the session is created the first time it is used.
:meth:`~scrapy.sessions.Sessions.create` covers the case where you have no ID of
your own to give: it returns a session that is certainly new, which indexing
cannot promise, since the ID you choose may be in use already.

.. skip: next
.. code-block:: python

    session = self.crawler.sessions.create()
    yield Request(url, meta={"session": session.id})

The follow-up requests that a spider callback yields stay in the session of the
request that got that callback its response, so a session lasts as long as the
crawl that follows from it without its ID being passed along by hand. Set
:reqmeta:`session` on one of those requests to move it to a different session.

A request that neither sets :reqmeta:`session` nor inherits one uses the session
whose ID is ``"main"``. Everything a crawl does without asking for a session
happens there, which makes ``session="main"`` the way to send a request back to
it, e.g. from a callback whose own session is a different one.

Set :reqmeta:`session` to ``None`` for a request to use no session at all: no
stored cookie is sent with it and no cookie received in its response is stored.
The cookies of the request itself are still sent, and its follow-up requests
inherit the lack of a session.


.. _session-registry:

The session registry
====================

.. versionadded:: VERSION

Sessions live in :attr:`Crawler.sessions <scrapy.crawler.Crawler.sessions>`,
where you can inspect and modify them:

.. skip: start
.. code-block:: pycon

    >>> cookies = crawler.sessions["main"].cookies
    >>> len(cookies)
    2
    >>> cookies.clear()

.. skip: end

When a session stops working, e.g. because the website expired it, call
:meth:`~scrapy.sessions.Sessions.retire` and retry the request with
:func:`~scrapy.downloadermiddlewares.retry.get_retry_request`: the session is
gone, so the retry starts a new one under the same ID.

.. autoclass:: scrapy.sessions.Sessions
    :members:

.. autoclass:: scrapy.sessions.Session
    :members:


Sending cookies with a request
==============================

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
i.e. if the request has a session.

.. caution:: Cookies set through the ``Cookie`` header are not handled by
    :class:`~scrapy.downloadermiddlewares.cookies.CookiesMiddleware`, which
    drops that header.

.. caution:: When a cookie name or value is a byte sequence that is not UTF-8
    encoded, the cookie is dropped and a warning is logged. See
    :ref:`topics-logging-advanced-customization` to customize the logging
    behavior.


.. setting:: SESSIONS_MAX

SESSIONS_MAX
============

Default: ``1000``

Maximum number of sessions to keep in memory. When the limit is reached, the
session that has not been used for the longest time is dropped, losing its
cookies. The first drop is logged as a warning, and :stat:`sessions/dropped`
counts them all.

Raise it if a crawl needs more sessions alive at the same time, e.g. because it
gives every request a session of its own.


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

.. autoclass:: CookiesMiddleware
