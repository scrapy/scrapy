.. _bans:

=============
Avoiding bans
=============

This topic covers some of the strategies that you can follow to avoid getting
different or bad responses from a website that you are crawling due to filters
such as regional filters, web browser filters, etc.

.. _avoiding-crawls:

Avoiding crawls
===============

The best way not to be banned from a website is not to send requests to it in
the first place.

One way to avoid crawling a website is to find the desired dataset through
other means. For example, you can use Google’s `dataset search engine`_.

If the target website is the only or best source of the desired information,
and you only need to extract the data on a monthly basis or a lower frequency,
you may be able to crawl a public snapshot of the target website instead.
`Common Crawl`_ is an open repository of web crawl data that you can access
freely. It contains monthly snapshots of a wide variety of websites and, if you
are lucky, your target website will be among them.

.. _Common Crawl: https://commoncrawl.org/
.. _dataset search engine: https://datasetsearch.research.google.com/


.. _being-polite:

Being polite
============

To avoid being banned, you should first avoid giving a website reasons to ban
you.

.. _identifying-yourself:

Identifying yourself
--------------------

If your crawling has a noticeable negative impact on a website or you crawl
content that should not be crawled, website administrators will need to do
something.

Set :setting:`USER_AGENT` to a value that uniquely identifies your spider and
includes contact information, so that website administrators can contact you.


.. _following-robotstxt:

Following robots.txt guidelines
-------------------------------

Some websites provide a ``robots.txt`` file at their root path (e.g.
``http://example.com/robots.txt``) that describes the guidelines that they wish
bots to follow when crawling their website.

Before you start writing a spider for a website, read their ``robots.txt``
file and implement your spider following its guidelines. See the `robots.txt
standard draft`_ or the `robots.txt Google specification`_ for information on
how to read ``robots.txt`` files.

To ensure that your spider does not crawl pages restricted by ``robots.txt``
guidelines, set :setting:`ROBOTSTXT_OBEY` to ``True`` to enable the
:class:`~scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware`
middleware. When you do, if your spider attempts to crawl a restricted page,
this middleware aborts that request with the following message::

    Forbidden by robots.txt

Also set :setting:`CONCURRENT_REQUESTS_PER_DOMAIN` and
:setting:`DOWNLOAD_DELAY` to values that comply with the ``Crawl-Delay`` or
``Request-Rate`` directives from the ``robots.txt`` guidelines.

You may also use the :ref:`AutoThrottle extension <topics-autothrottle>` on top
of that, so that when the target website experiences a high load, your spider
automatically switches to higher download delays.

.. _robots.txt Google specification: https://developers.google.com/search/reference/robots_txt
.. _robots.txt standard draft: https://tools.ietf.org/html/draft-koster-rep-00


.. _choosing-crawl-speed:

Finding the right guidelines on your own
----------------------------------------

If a website does not specify a desired download delay, or does not provide a
``robots.txt`` file, you should make an effort to find out the right values for
:setting:`CONCURRENT_REQUESTS_PER_DOMAIN` and :setting:`DOWNLOAD_DELAY` that
will not have a noticeable negative impact on the target website.

Use a service like `SimilarWeb`_ to find out the amount of monthly traffic that
the target website receives, and choose concurrency and delay values that will
not cause a noticeable traffic increase.

.. _SimilarWeb: https://www.similarweb.com


.. _filters-and-challenges:

Bypassing filters and solving challenges
========================================

Some websites implement filters and challenges that aim to deny access or alter
their content based on aspects of the visitor, such as the country where they
are or the web browsing tool they use.

.. _regional-filter:

Bypassing regional filters
--------------------------

Some websites send different or bad responses based on the region or country
associated to your `IP address`_.

To bypass these filters, get access to a `proxy server`_ that has an outgoing
IP address from a region that gets the desired responses.

Use the :class:`~scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware`
middleware to configure your spider to use that proxy.

.. _IP address: https://en.wikipedia.org/wiki/IP_address
.. _proxy server: https://en.wikipedia.org/wiki/Proxy_server


.. _web-browser-filter:

Bypassing web browser filters
-----------------------------

Some websites send different or bad responses if they detect that your request
does not come from a web browser.

To bypass these filters, switch your :setting:`USER_AGENT` to a value copied
from those that popular web browsers use. In some rare cases, you may need a
user agent string from a specific web browser.

There are multiple Scrapy plugins that can rotate your requests through popular
web browser user agent strings, such as scrapy-fake-useragent_,
scrapy-random-useragent_ or Scrapy-UserAgents_.

For advanced web browser filters,
:ref:`pre-rendering JavaScript <topics-javascript-rendering>` or
:ref:`using a headless browser <topics-headless-browsing>` may be necessary.
Use these options only as a last resort, however, because they cause a higher
load per request on the target website.

.. _scrapy-fake-useragent: https://github.com/alecxe/scrapy-fake-useragent
.. _scrapy-random-useragent: https://github.com/cleocn/scrapy-random-useragent
.. _Scrapy-UserAgents: https://pypi.org/project/Scrapy-UserAgents/


.. _request-delay-filter:

Bypassing request delay filters
-------------------------------

Some websites may ban your IP after they detect that your requests use a
constant download delay.

To help bypassing these filters, the :setting:`RANDOMIZE_DOWNLOAD_DELAY`
setting is enabled by default. When that is not enough, an
:ref:`IP address rotation solution <ip-rotation>` may be much more effective.


.. _isp-filter:

Bypassing internet service provider filters
-------------------------------------------

Some websites send different or bad responses if they detect that your request
comes from an IP address that belongs to a `data center`_, as opposed to a
residential IP address from an `internet service provider`_ or a mobile IP
address from a `mobile network`_.

To bypass these filters, get access to a proxy server that has an outgoing IP
address that is either residential or mobile. Note that you may also get
different responses depending on whether your IP address is residential or
mobile.

Use the :class:`~scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware`
middleware to configure your spider to use that proxy.

.. _data center: https://en.wikipedia.org/wiki/Data_center
.. _internet service provider: https://en.wikipedia.org/wiki/Internet_service_provider
.. _mobile network: https://en.wikipedia.org/wiki/Cellular_network


.. _captcha:

Solving CAPTCHA challenges
--------------------------

Some websites require you to solve a `CAPTCHA challenge`_ to get the desired
response.

To bypass these filters, several options exist:

-   You could have your spider present the CAPTCHA challenge to you and wait
    for you to solve it manually.

-   Some CAPTCHA challenges can be solved using an `optical character
    recognition`_ (OCR) solution such as pytesseract_.

-   Paid CAPTCHA solving services exist.

Whichever solution you choose, implement it as a :ref:`downloader middleware
<topics-downloader-middleware>` that automatically detects CAPTCHA challenges
in responses and solves them, so that your spider code only receives successful
responses.

.. _CAPTCHA challenge: https://en.wikipedia.org/wiki/CAPTCHA
.. _optical character recognition: https://en.wikipedia.org/wiki/Optical_character_recognition
.. _pytesseract: https://github.com/madmaze/pytesseract


.. _ip-rotation:

IP address rotation solutions
=============================

See below some of the different solutions there are to have your requests use
different outgoing IP addresses.

When using this approach, remember to set :setting:`COOKIES_ENABLED` to
``False`` to disable global cookie handling. This prevents websites from
identifying two requests as coming from the same user agent even if they come
from different IP addresses and have different user-agent strings. You can
still include some cookies manually in your requests. Define them through the
``Cookies`` header of your requests. See
:class:`Request.headers <scrapy.http.Request.headers>`.

.. _smart-proxy:

Smart proxies
-------------

An increasing number of websites use solutions that apply many of the above
filters and challenges at the same time.

There are paid proxy services, like `Zyte Smart Proxy Manager`_, that
automatically bypass website filters and challenges, so that your spider only
gets successful responses. They also allow managing sessions to simulate user
behavior.

For Zyte Smart Proxy Manager, installing scrapy-crawlera_ will offer advanced
integration with Scrapy. For other services, use the
:class:`~scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware` middleware
or implement your own :ref:`downloader middleware
<topics-downloader-middleware>`.

.. _scrapy-crawlera: https://scrapy-crawlera.readthedocs.io/en/latest/
.. _Zyte Smart Proxy Manager: https://www.zyte.com/smart-proxy-manager/


.. _rotating-proxy:

Rotating proxies
----------------

Rotating proxy services like ProxyMesh_ send different requests through
different proxies. This can decrease the likelihood of being affected by some
filters or challenges.

.. _ProxyMesh: https://proxymesh.com/


.. _free-proxies:

Free proxies
------------

You can easily find lists of free proxies in the internet, and you can use
a solution like `scrapy-rotating-proxies`_ to configure multiple proxies in
your spider and have requests rotate through them automatically.

This approach, however, has serious drawbacks:

-   Free proxies may stop working at any moment. You need to implement a way to
    refresh your list of free proxies.

-   In addition to handling occasional bad responses from websites, you
    need to handle all kinds of bad responses from proxies. You may even need
    to inspect the response body to determine if a response comes from the
    target website or from a misbehaving proxy.

-   Advanced antibot solutions may automatically detect and filter out traffic
    from free proxies.

.. _scrapy-rotating-proxies: https://github.com/TeamHG-Memex/scrapy-rotating-proxies


.. _custom-rotating-proxy:

Custom rotating proxy
---------------------

If you have spare servers, you can set them up as proxies and use scrapoxy_ to
build a custom proxy that rotates traffic through them. However, the initial
setup can be complex, and your requests will be vulnerable to
:ref:`internet service provider filtering <isp-filter>`.

.. _scrapoxy: https://scrapoxy.io/


.. _tor:

The Tor network
---------------

It is possible to send requests through the `Tor network`_.

The initial setup to have Scrapy working with Tor is not straightforward.
Use a search engine to find up-to-date documentation specific to using
Scrapy and Tor together.

The main drawback of using the Tor network is that traffic can be extremely
slow.

.. _Tor network: https://en.wikipedia.org/wiki/Tor_(anonymity_network)


.. _commercial-support:

Seeking professional help
=========================

Avoiding bans, filters and challenges can be difficult and tricky, and may
sometimes require special infrastructure.

If you find yourself unable to prevent your spider from getting bad responses,
consider contacting `commercial support`_.

.. _commercial support: https://scrapy.org/support/
