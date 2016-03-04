.. _intro-overview:

==================
Scrapy at a glance
==================

Scrapy is an application framework for crawling web sites and extracting
structured data which can be used for a wide range of useful applications, like
data mining, information processing or historical archival.

Even though Scrapy was originally designed for `web scraping`_, it can also be
used to extract data using APIs (such as `Amazon Associates Web Services`_) or
as a general purpose web crawler.


Walk-through of an example spider
=================================

In order to show you what Scrapy brings to the table, we'll walk you through an
example of a Scrapy Spider using the simplest way to run a spider.

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
            yield {
                'title': response.css('h1 a::text').extract()[0],
                'votes': response.css('.question .vote-count-post::text').extract()[0],
                'body': response.css('.question .post-text').extract()[0],
                'tags': response.css('.question .post-tag::text').extract(),
                'link': response.url,
            }


Put this in a file, name it to something like ``stackoverflow_spider.py``
and run the spider using the :command:`runspider` command::

    scrapy runspider stackoverflow_spider.py -o top-stackoverflow-questions.json


When this finishes you will have in the ``top-stackoverflow-questions.json`` file
a list of the most upvoted questions in StackOverflow in JSON format, containing the
title, link, number of upvotes, a list of the tags and the question content in HTML,
looking like this (reformatted for easier reading)::

    [{
        "body": "... LONG HTML HERE ...",
        "link": "http://stackoverflow.com/questions/11227809/why-is-processing-a-sorted-array-faster-than-an-unsorted-array",
        "tags": ["java", "c++", "performance", "optimization"],
        "title": "Why is processing a sorted array faster than an unsorted array?",
        "votes": "9924"
    },
    {
        "body": "... LONG HTML HERE ...",
        "link": "http://stackoverflow.com/questions/1260748/how-do-i-remove-a-git-submodule",
        "tags": ["git", "git-submodules"],
        "title": "How do I remove a Git submodule?",
        "votes": "1764"
    },
    ...]



What just happened?
-------------------

When you ran the command ``scrapy runspider somefile.py``, Scrapy looked for a
Spider definition inside it and ran it through its crawler engine.

The crawl started by making requests to the URLs defined in the ``start_urls``
attribute (in this case, only the URL for StackOverflow top questions page)
and called the default callback method ``parse``, passing the response object as
an argument. In the ``parse`` callback we extract the links to the
question pages using a CSS Selector with a custom extension that allows to get
the value for an attribute. Then we yield a few more requests to be sent,
registering the method ``parse_question`` as the callback to be called for each
of them as they finish.

Here you notice one of the main advantages about Scrapy: requests are
:ref:`scheduled and processed asynchronously <topics-architecture>`.  This
means that Scrapy doesn't need to wait for a request to be finished and
processed, it can send another request or do other things in the meantime. This
also means that other requests can keep going even if some request fails or an
error happens while handling it.

While this enables you to do very fast crawls (sending multiple concurrent
requests at the same time, in a fault-tolerant way) Scrapy also gives you
control over the politeness of the crawl through :ref:`a few settings
<topics-settings-ref>`. You can do things like setting a download delay between
each request, limiting amount of concurrent requests per domain or per IP, and
even :ref:`using an auto-throttling extension <topics-autothrottle>` that tries
to figure out these automatically.

Finally, the ``parse_question`` callback scrapes the question data for each
page yielding a dict, which Scrapy then collects and writes to a JSON file as
requested in the command line.

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

* Built-in support for :ref:`selecting and extracting <topics-selectors>` data
  from HTML/XML sources using extended CSS selectors and XPath expressions,
  with helper methods to extract using regular expressions.

* An :ref:`interactive shell console <topics-shell>` (IPython aware) for trying
  out the CSS and XPath expressions to scrape data, very useful when writing or
  debugging your spiders.

* Built-in support for :ref:`generating feed exports <topics-feed-exports>` in
  multiple formats (JSON, CSV, XML) and storing them in multiple backends (FTP,
  S3, local filesystem)

* Robust encoding support and auto-detection, for dealing with foreign,
  non-standard and broken encoding declarations.

* :ref:`Strong extensibility support <extending-scrapy>`, allowing you to plug
  in your own functionality using :ref:`signals <topics-signals>` and a
  well-defined API (middlewares, :ref:`extensions <topics-extensions>`, and
  :ref:`pipelines <topics-item-pipeline>`).

* Wide range of built-in extensions and middlewares for handling:
    * cookies and session handling
    * HTTP features like compression, authentication, caching
    * user-agent spoofing
    * robots.txt
    * crawl depth restriction
    * and more

* A :ref:`Telnet console <topics-telnetconsole>` for hooking into a Python
  console running inside your Scrapy process, to introspect and debug your
  crawler

* Plus other goodies like reusable spiders to crawl sites from `Sitemaps`_ and
  XML/CSV feeds, a media pipeline for :ref:`automatically downloading images
  <topics-media-pipeline>` (or any other media) associated with the scraped
  items, a caching DNS resolver, and much more!

What's next?
============

The next steps for you are to :ref:`install Scrapy <intro-install>`,
:ref:`follow through the tutorial <intro-tutorial>` to learn how to organize
your code in Scrapy projects and `join the community`_. Thanks for your
interest!

.. _join the community: http://scrapy.org/community/
.. _web scraping: https://en.wikipedia.org/wiki/Web_scraping
.. _Amazon Associates Web Services: https://affiliate-program.amazon.com/gp/advertising/api/detail/main.html
.. _Amazon S3: https://aws.amazon.com/s3/
.. _Sitemaps: http://www.sitemaps.org
