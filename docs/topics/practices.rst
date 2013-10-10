.. _topics-practices:

================
Common Practices
================

This section documents common practices when using Scrapy. These are things
that cover many topics and don't often fall into any other specific section.

.. _run-from-script:

Run Scrapy from a script
========================

You can use the :ref:`API <topics-api>` to run Scrapy from a script, instead of
the typical way of running Scrapy via ``scrapy crawl``.

Remember that Scrapy is built on top of the Twisted
asynchronous networking library, so you need run it inside the Twisted reactor.

Note that you will also have to shutdown the Twisted reactor yourself after the
spider is finished. This can be achieved by connecting a handler to the
``signals.spider_closed`` signal.

What follows is a working example of how to do that, using the `testspiders`_
project as example.

::

    from twisted.internet import reactor
    from scrapy.crawler import Crawler
    from scrapy.settings import Settings
    from scrapy import log, signals
    from testspiders.spiders.followall import FollowAllSpider

    spider = FollowAllSpider(domain='scrapinghub.com')
    crawler = Crawler(Settings())
    crawler.signals.connect(reactor.stop, signal=signals.spider_closed)
    crawler.configure()
    crawler.crawl(spider)
    crawler.start()
    log.start()
    reactor.run() # the script will block here until the spider_closed signal was sent

.. seealso:: `Twisted Reactor Overview`_.

Running multiple spiders in the same process
============================================

By default, Scrapy runs a single spider per process when you run ``scrapy
crawl``. However, Scrapy supports running multiple spiders per process using
the :ref:`internal API <topics-api>`.

Here is an example, using the `testspiders`_ project:

::

    from twisted.internet import reactor
    from scrapy.crawler import Crawler
    from scrapy.settings import Settings
    from scrapy import log
    from testspiders.spiders.followall import FollowAllSpider

    def setup_crawler(domain):
        spider = FollowAllSpider(domain=domain)
        crawler = Crawler(Settings())
        crawler.configure()
        crawler.crawl(spider)
        crawler.start()

    for domain in ['scrapinghub.com', 'insophia.com']:
        setup_crawler(domain)
    log.start()
    reactor.run()

.. seealso:: :ref:`run-from-script`.

.. _distributed-crawls:

Distributed crawls
==================

Scrapy doesn't provide any built-in facility for running crawls in a distribute
(multi-server) manner. However, there are some ways to distribute crawls, which
vary depending on how you plan to distribute them.

If you have many spiders, the obvious way to distribute the load is to setup
many Scrapyd instances and distribute spider runs among those.

If you instead want to run a single (big) spider through many machines, what
you usually do is partition the urls to crawl and send them to each separate
spider. Here is a concrete example:

First, you prepare the list of urls to crawl and put them into separate
files/urls::

    http://somedomain.com/urls-to-crawl/spider1/part1.list
    http://somedomain.com/urls-to-crawl/spider1/part2.list
    http://somedomain.com/urls-to-crawl/spider1/part3.list

Then you fire a spider run on 3 different Scrapyd servers. The spider would
receive a (spider) argument ``part`` with the number of the partition to
crawl::

    curl http://scrapy1.mycompany.com:6800/schedule.json -d project=myproject -d spider=spider1 -d part=1
    curl http://scrapy2.mycompany.com:6800/schedule.json -d project=myproject -d spider=spider1 -d part=2
    curl http://scrapy3.mycompany.com:6800/schedule.json -d project=myproject -d spider=spider1 -d part=3

.. _bans:

Avoiding getting banned
=======================

Some websites implement certain measures to prevent bots from crawling them,
with varying degrees of sophistication. Getting around those measures can be
difficult and tricky, and may sometimes require special infrastructure. Please
consider contacting `commercial support`_ if in doubt.

Here are some tips to keep in mind when dealing with these kind of sites:

* rotate your user agent from a pool of well-known ones from browsers (google
  around to get a list of them)
* disable cookies (see :setting:`COOKIES_ENABLED`) as some sites may use
  cookies to spot bot behaviour
* use download delays (2 or higher). See :setting:`DOWNLOAD_DELAY` setting.
* if possible, use `Google cache`_ to fetch pages, instead of hitting the sites
  directly
* use a pool of rotating IPs. For example, the free `Tor project`_ or paid
  services like `ProxyMesh`_
* use a highly distributed downloader that circumvents bans internally, so you
  can just focus on parsing clean pages. One example of such downloaders is
  `Crawlera`_

If you are still unable to prevent your bot getting banned, consider contacting
`commercial support`_.

.. _Tor project: https://www.torproject.org/
.. _commercial support: http://scrapy.org/support/
.. _ProxyMesh: http://proxymesh.com/
.. _Google cache: http://www.googleguide.com/cached_pages.html
.. _testspiders: https://github.com/scrapinghub/testspiders
.. _Twisted Reactor Overview: http://twistedmatrix.com/documents/current/core/howto/reactor-basics.html
.. _Crawlera: http://crawlera.com
