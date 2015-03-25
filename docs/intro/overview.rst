.. _intro-overview:

==================
Scrapy at a glance
==================

Scrapy is an application framework for crawling web sites and extracting
structured data which can be used for a wide range of useful applications, like
data mining, information processing or historical archival.

Even though Scrapy was originally designed for `screen scraping`_ (more
precisely, `web scraping`_), it can also be used to extract data using APIs
(such as `Amazon Associates Web Services`_) or as a general purpose web
crawler.


Walk-through of an example spider
=================================

In order to show you what Scrapy brings to the table, we'll walk you
through an example of a Scrapy Spider using the simplest way to run a spider.

Once you're ready to dive in more, you can :ref:`follow the tutorial
and build a full-blown Scrapy project <intro-tutorial>`.

So, here's the code for a spider that follows the links to the top
voted questions on StackOverflow and scrapes some data from each page::

    import scrapy


    class StackOverflowSpider(scrapy.Spider):
        name = 'stackoverflow'
        start_urls = ['http://stackoverflow.com/questions?sort=votes']

        def parse(self, response):
            for href in response.css('.question-summary h3 a::attr(href)'):
                full_url = response.urljoin(href.extract())
                yield scrapy.Request(full_url, callback=self.parse_question)

        def parse_question(self, response):
            title = response.css('h1 a::text').extract_first()
            votes = response.css('.question .vote-count-post::text').extract_first()
            tags = response.css('.question .post-tag::text').extract()
            body = response.css('.question .post-text').extract_first()
            yield {
                'title': title,
                'votes': votes,
                'body': body,
                'tags': tags,
                'link': response.url,
            }


Put this in a file, name it to something like ``stackoverflow_spider.py``
and run the spider using the :command:`runspider` command::

    scrapy runspider stackoverflow_spider.py -o top-stackoverflow-questions.json


When this finishes you will have in the ``top-stackoverflow-questions.json`` file
a list of the most upvoted questions in StackOverflow in JSON format, containing the
title, link, number of upvotes, a list of the tags and the question content in HTML.


What just happened?
-------------------

When you ran the command ``scrapy runspider somefile.py``, Scrapy looked
for a Spider definition inside it and ran it through its crawler engine.

The crawl started by making requests to the URLs defined in the ``start_urls``
attribute (in this case, only the URL for StackOverflow top questions page),
and then called the default callback method ``parse`` passing the response
object as an argument.

In the ``parse`` callback, we scrape the links to the questions and
yield a few more requests to be processed, registering for them
the method ``parse_question`` as the callback to be called when the
requests are complete.

Finally, the ``parse_question`` callback scrapes the question data
for each page yielding a dict, which Scrapy then collects and
writes to a JSON file as requested in the command line.

.. note::

    This is using :ref:`feed exports <topics-feed-exports>` to generate the
    JSON file, you can easily change the export format (XML or CSV, for example) or the
    storage backend (FTP or `Amazon S3`_, for example).  You can also write an
    :ref:`item pipeline <topics-item-pipeline>` to store the items in a database.


.. _topics-whatelse:

What else?
==========

You've seen how to extract and store items from a website using Scrapy, but
this is just the surface. Scrapy provides a lot of powerful features for making
scraping easy and efficient, such as:

* An :ref:`interactive shell console <topics-shell>` (IPython aware) for trying
  out the CSS and XPath expressions to scrape data, very useful when writing or
  debugging your spiders.

* Built-in support for :ref:`generating feed exports <topics-feed-exports>` in
  multiple formats (JSON, CSV, XML) and storing them in multiple backends (FTP,
  S3, local filesystem)

* Robust encoding support and auto-detection, for dealing with foreign,
  non-standard and broken encoding declarations.

* Strong :ref:`extensibility support <extending-scrapy>` and lots of built-in
  extensions and middlewares to handle things like cookies, crawl throttling,
  HTTP caching, HTTP compression, user-agent spoofing, robots.txt,
  stats collection and many more.

* A :ref:`Telnet console <topics-telnetconsole>` for hooking into a Python
  console running inside your Scrapy process, to introspect and debug your
  crawler

* A caching DNS resolver

* Support for crawling based on URLs discovered through `Sitemaps`_

* A media pipeline for :ref:`automatically downloading images <topics-images>`
  (or any other media) associated with the scraped items

What's next?
============

The next obvious steps for you are to `download Scrapy`_, read :ref:`the
tutorial <intro-tutorial>` and join `the community`_. Thanks for your
interest!

.. _download Scrapy: http://scrapy.org/download/
.. _the community: http://scrapy.org/community/
.. _screen scraping: http://en.wikipedia.org/wiki/Screen_scraping
.. _web scraping: http://en.wikipedia.org/wiki/Web_scraping
.. _Amazon Associates Web Services: http://aws.amazon.com/associates/
.. _Amazon S3: http://aws.amazon.com/s3/
.. _Sitemaps: http://www.sitemaps.org
