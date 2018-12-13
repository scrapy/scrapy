.. _topics-signals:

=======
Signals
=======

Scrapy uses signals extensively to notify when certain events occur. You can
catch some of those signals in your Scrapy project (using an :ref:`extension
<topics-extensions>`, for example) to perform additional tasks or extend Scrapy
to add functionality not provided out of the box.

Even though signals provide several arguments, the handlers that catch them
don't need to accept all of them - the signal dispatching mechanism will only
deliver the arguments that the handler receives.

You can connect to signals (or send your own) through the
:ref:`topics-api-signals`.

Here is a simple example showing how you can catch signals and perform some action:
::

    from scrapy import signals
    from scrapy import Spider


    class DmozSpider(Spider):
        name = "dmoz"
        allowed_domains = ["dmoz.org"]
        start_urls = [
            "http://www.dmoz.org/Computers/Programming/Languages/Python/Books/",
            "http://www.dmoz.org/Computers/Programming/Languages/Python/Resources/",
        ]


        @classmethod
        def from_crawler(cls, crawler, *args, **kwargs):
            spider = super(DmozSpider, cls).from_crawler(crawler, *args, **kwargs)
            crawler.signals.connect(spider.spider_closed, signal=signals.spider_closed)
            return spider


        def spider_closed(self, spider):
            spider.logger.info('Spider closed: %s', spider.name)


        def parse(self, response):
            pass


Deferred signal handlers
========================

Some signals support returning `Twisted deferreds`_ from their handlers, see
the :ref:`topics-signals-ref` to know which ones.

.. _Twisted deferreds: https://twistedmatrix.com/documents/current/core/howto/defer.html
