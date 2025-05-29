.. _topics-practices:

================
Common Practices
================

This section documents common practices when using Scrapy. These are things
that cover many topics and don't often fall into any other specific section.

.. skip: start

.. _run-from-script:

Run Scrapy from a script
========================

You can use the :ref:`API <topics-api>` to run Scrapy from a script, instead of
the typical way of running Scrapy via ``scrapy crawl``.

Remember that Scrapy is built on top of the Twisted
asynchronous networking library, so you need to run it inside the Twisted reactor.

The first utility you can use to run your spiders is
:class:`scrapy.crawler.AsyncCrawlerProcess` or
:class:`scrapy.crawler.CrawlerProcess`. These classes will start a Twisted
reactor for you, configuring the logging and setting shutdown handlers. These
classes are the ones used by all Scrapy commands. They have similar
functionality, differing in their asynchronous API style:
:class:`~scrapy.crawler.AsyncCrawlerProcess` returns coroutines from its
asynchronous methods while :class:`~scrapy.crawler.CrawlerProcess` returns
:class:`~twisted.internet.defer.Deferred` objects.

Here's an example showing how to run a single spider with it.

.. code-block:: python

    import scrapy
    from scrapy.crawler import AsyncCrawlerProcess


    class MySpider(scrapy.Spider):
        # Your spider definition
        ...


    process = AsyncCrawlerProcess(
        settings={
            "FEEDS": {
                "items.json": {"format": "json"},
            },
        }
    )

    process.crawl(MySpider)
    process.start()  # the script will block here until the crawling is finished

You can define :ref:`settings <topics-settings>` within the dictionary passed
to :class:`~scrapy.crawler.AsyncCrawlerProcess`. Make sure to check the
:class:`~scrapy.crawler.AsyncCrawlerProcess`
documentation to get acquainted with its usage details.

If you are inside a Scrapy project there are some additional helpers you can
use to import those components within the project. You can automatically import
your spiders passing their name to
:class:`~scrapy.crawler.AsyncCrawlerProcess`, and use
:func:`scrapy.utils.project.get_project_settings` to get a
:class:`~scrapy.settings.Settings` instance with your project settings.

What follows is a working example of how to do that, using the `testspiders`_
project as example.

.. code-block:: python

    from scrapy.crawler import AsyncCrawlerProcess
    from scrapy.utils.project import get_project_settings

    process = AsyncCrawlerProcess(get_project_settings())

    # 'followall' is the name of one of the spiders of the project.
    process.crawl("followall", domain="scrapy.org")
    process.start()  # the script will block here until the crawling is finished

There's another Scrapy utility that provides more control over the crawling
process: :class:`scrapy.crawler.AsyncCrawlerRunner` or
:class:`scrapy.crawler.CrawlerRunner`. These classes are thin wrappers
that encapsulate some simple helpers to run multiple crawlers, but they won't
start or interfere with existing reactors in any way. Just like
:class:`scrapy.crawler.AsyncCrawlerProcess` and
:class:`scrapy.crawler.CrawlerProcess` they differ in their asynchronous API
style.

When using these classes the reactor should be explicitly run after scheduling
your spiders. It's recommended that you use
:class:`~scrapy.crawler.AsyncCrawlerRunner` or
:class:`~scrapy.crawler.CrawlerRunner` instead of
:class:`~scrapy.crawler.AsyncCrawlerProcess` or
:class:`~scrapy.crawler.CrawlerProcess` if your application is already using
Twisted and you want to run Scrapy in the same reactor.

If you want to stop the reactor or run any other code right after the spider
finishes you can do that after the task returned from
:meth:`AsyncCrawlerRunner.crawl() <scrapy.crawler.AsyncCrawlerRunner.crawl>`
completes (or the Deferred returned from :meth:`CrawlerRunner.crawl()
<scrapy.crawler.CrawlerRunner.crawl>` fires). In the simplest case you can also
use :func:`twisted.internet.task.react` to start and stop the reactor, though
it may be easier to just use :class:`~scrapy.crawler.AsyncCrawlerProcess` or
:class:`~scrapy.crawler.CrawlerProcess` instead.

Here's an example of using :class:`~scrapy.crawler.AsyncCrawlerRunner` together
with simple reactor management code:

.. code-block:: python

    import scrapy
    from scrapy.crawler import AsyncCrawlerRunner
    from scrapy.utils.defer import deferred_f_from_coro_f
    from scrapy.utils.log import configure_logging
    from scrapy.utils.reactor import install_reactor
    from twisted.internet.task import react


    class MySpider(scrapy.Spider):
        # Your spider definition
        ...


    async def crawl(_):
        configure_logging({"LOG_FORMAT": "%(levelname)s: %(message)s"})
        runner = AsyncCrawlerRunner()
        await runner.crawl(MySpider)  # completes when the spider finishes


    install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")
    react(deferred_f_from_coro_f(crawl))

Same example but using :class:`~scrapy.crawler.CrawlerRunner` and a
different reactor (:class:`~scrapy.crawler.AsyncCrawlerRunner` only works
with :class:`~twisted.internet.asyncioreactor.AsyncioSelectorReactor`):

.. code-block:: python

    import scrapy
    from scrapy.crawler import CrawlerRunner
    from scrapy.utils.log import configure_logging
    from scrapy.utils.reactor import install_reactor
    from twisted.internet.task import react


    class MySpider(scrapy.Spider):
        custom_settings = {
            "TWISTED_REACTOR": "twisted.internet.epollreactor.EPollReactor",
        }
        # Your spider definition
        ...


    def crawl(_):
        configure_logging({"LOG_FORMAT": "%(levelname)s: %(message)s"})
        runner = CrawlerRunner()
        d = runner.crawl(MySpider)
        return d  # this Deferred fires when the spider finishes


    install_reactor("twisted.internet.epollreactor.EPollReactor")
    react(crawl)

.. seealso:: :doc:`twisted:core/howto/reactor-basics`

.. _run-multiple-spiders:

Running multiple spiders in the same process
============================================

By default, Scrapy runs a single spider per process when you run ``scrapy
crawl``. However, Scrapy supports running multiple spiders per process using
the :ref:`internal API <topics-api>`.

Here is an example that runs multiple spiders simultaneously:

.. code-block:: python

    import scrapy
    from scrapy.crawler import AsyncCrawlerProcess
    from scrapy.utils.project import get_project_settings


    class MySpider1(scrapy.Spider):
        # Your first spider definition
        ...


    class MySpider2(scrapy.Spider):
        # Your second spider definition
        ...


    settings = get_project_settings()
    process = AsyncCrawlerProcess(settings)
    process.crawl(MySpider1)
    process.crawl(MySpider2)
    process.start()  # the script will block here until all crawling jobs are finished

Same example using :class:`~scrapy.crawler.AsyncCrawlerRunner`:

.. code-block:: python

    import scrapy
    from scrapy.crawler import AsyncCrawlerRunner
    from scrapy.utils.defer import deferred_f_from_coro_f
    from scrapy.utils.log import configure_logging
    from scrapy.utils.reactor import install_reactor
    from twisted.internet.task import react


    class MySpider1(scrapy.Spider):
        # Your first spider definition
        ...


    class MySpider2(scrapy.Spider):
        # Your second spider definition
        ...


    async def crawl(_):
        configure_logging({"LOG_FORMAT": "%(levelname)s: %(message)s"})
        runner = AsyncCrawlerRunner()
        runner.crawl(MySpider1)
        runner.crawl(MySpider2)
        await runner.join()  # completes when both spiders finish


    install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")
    react(deferred_f_from_coro_f(crawl))


Same example but running the spiders sequentially by awaiting until each one
finishes before starting the next one:

.. code-block:: python

    import scrapy
    from scrapy.crawler import AsyncCrawlerRunner
    from scrapy.utils.defer import deferred_f_from_coro_f
    from scrapy.utils.log import configure_logging
    from scrapy.utils.reactor import install_reactor
    from twisted.internet.task import react


    class MySpider1(scrapy.Spider):
        # Your first spider definition
        ...


    class MySpider2(scrapy.Spider):
        # Your second spider definition
        ...


    async def crawl(_):
        configure_logging({"LOG_FORMAT": "%(levelname)s: %(message)s"})
        runner = AsyncCrawlerRunner()
        await runner.crawl(MySpider1)
        await runner.crawl(MySpider2)


    install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")
    react(deferred_f_from_coro_f(crawl))

.. note:: When running multiple spiders in the same process, :ref:`reactor
    settings <reactor-settings>` should not have a different value per spider.
    Also, :ref:`pre-crawler settings <pre-crawler-settings>` cannot be defined
    per spider.

.. seealso:: :ref:`run-from-script`.

.. skip: end

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

Here are some tips to keep in mind when dealing with these kinds of sites:

* rotate your user agent from a pool of well-known ones from browsers (google
  around to get a list of them)
* disable cookies (see :setting:`COOKIES_ENABLED`) as some sites may use
  cookies to spot bot behaviour
* use download delays (2 or higher). See :setting:`DOWNLOAD_DELAY` setting.
* if possible, use `Common Crawl`_ to fetch pages, instead of hitting the sites
  directly
* use a pool of rotating IPs. For example, the free `Tor project`_ or paid
  services like `ProxyMesh`_. An open source alternative is `scrapoxy`_, a
  super proxy that you can attach your own proxies to.
* use a ban avoidance service, such as `Zyte API`_, which provides a `Scrapy
  plugin <https://github.com/scrapy-plugins/scrapy-zyte-api>`__ and additional
  features, like `AI web scraping <https://www.zyte.com/ai-web-scraping/>`__

If you are still unable to prevent your bot getting banned, consider contacting
`commercial support`_.

.. _Tor project: https://www.torproject.org/
.. _commercial support: https://scrapy.org/support/
.. _ProxyMesh: https://proxymesh.com/
.. _Common Crawl: https://commoncrawl.org/
.. _testspiders: https://github.com/scrapinghub/testspiders
.. _scrapoxy: https://scrapoxy.io/
.. _Zyte API: https://docs.zyte.com/zyte-api/get-started.html
