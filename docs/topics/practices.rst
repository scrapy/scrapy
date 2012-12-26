.. _topics-practices:

================
Common Practices
================

The section documents sommon common practices when using Scrapy. These are
things that don't often fall into other specific sections, or cover many of
them.

.. _run-from-script:

Run Scrapy from a script
========================

You can use the :ref:`API <topics-api>` to run script from a script, instead of
the typical way of running Scrapy via ``scrapy crawl``.

What follows is a working example of how to do that, using the `testspiders`_
project as example. Remember that Scrapy is asynchronous so you need run inside
the Twisted reactor.

::

    from twisted.internet import reactor
    from scrapy.crawler import Crawler
    from scrapy.settings import Settings
    from scrapy import log
    from testspiders.spiders.followall import FollowAllSpider

    spider = FollowAllSpider(domain='scrapinghub.com')
    crawler = Crawler(Settings())
    crawler.configure()
    crawler.crawl(spider)
    crawler.start()
    log.start()
    reactor.run() # the script will block here

Running multiple spiders in the same process
============================================

By default, Scrapy runs a single spider per process when you run ``scrapy
crawl``. However, Scrapy supports running multiple spiders per process if you
use the :ref:`internal API <topics-api>`.

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

See also: :ref:`run-from-script`.

.. _distributed-crawls:

Distributed crawls
==================

Scrapy doesn't provide any built-in facility to distribute crawls, however
there are some ways to distribute crawls, depending on what kind of crawling
you do.

If you have many spiders, the obvious way to distribute the load is to setup
many Scrapyd instances and distribute spider runs among those.

If you instead want to run a single (big) spider through many machines, what
you usually do is to partition the urls to crawl and send them to each separate
spider. Here is a concrete example:

First, you prepare a list of urls to crawl and put them into separate
files/urls::

    http://somedomain.com/urls-to-crawl/spider1/part1.list
    http://somedomain.com/urls-to-crawl/spider1/part2.list
    http://somedomain.com/urls-to-crawl/spider1/part3.list

Then you would fire a spider run on 3 different Scrapyd servers. The spider
would receive a spider argument ``part`` with the number of the partition to
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
* is possible, use `Google cache`_ to fetch pages, instead of hitting the sites
  directly
* use a pool of rotating IPs. For example, the free `Tor project`_ or paid
  services like `ProxyMesh`_

If you are still unable to prevent your bot getting banned, consider contacting
`commercial support`_.

.. _Tor project: https://www.torproject.org/
.. _commercial support: http://scrapy.org/support/
.. _ProxyMesh: http://proxymesh.com/
.. _Google cache: http://www.googleguide.com/cached_pages.html
.. _testspiders: https://github.com/scrapinghub/testspiders
