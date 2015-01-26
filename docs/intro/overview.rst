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

The purpose of this document is to introduce you to the concepts behind Scrapy
so you can get an idea of how it works and decide if Scrapy is what you need.

When you're ready to start a project, you can :ref:`start with the tutorial
<intro-tutorial>`.

Write a Spider
==============

So you need to extract some information from a website, but the website doesn't
provide any API or mechanism to access that info programmatically. Scrapy can
help you extract that information. You need to create Scrapy Spider.

A Spider is just an asynchronous web client surrounded by 
couple of mechanisms that are processing requests and data returned after
parsing responses. 

Spider gives you following benefits over plain synchronous HTTP library such 
as urllib or requests, Scrapy Spider:

* handles typical HTTP scenarios, for example manages cookies,
  redirects, retries on HTTP error codes, filters duplicate
  requests, limits spider speed, adds headers (such as 'User-Agent');
* is asynchronous (non-blocking), it can download and process requests 
  concurrently. This means that Scrapy Spider will always be faster 
  and more efficient then synchronous client;
* makes data extraction easier by allowing you to define common
  data models;
* allows you to isolate code that validates and processes data
  from code that extracts it and deals with response-request cycle, 
  you can define item pipelines that will process your data, and 
  middleware that will deal with responses and requests;
* is fault tolerant, exceptions in one callback processing
  spider responses do no affect other callbacks.

Let's illustrate these points by building simple
self-contained spider. Let's say we want to extract the URL, name and 
number of forks for trending Python repositories in Github. 
The list of trending repos can be found here: https://github.com/trending?l=python

We can see that this page displays name, url and number of stars for 
each repo, but it does not show number of forks. To get number of
forks we will have to make request to each repository page and extract
data from there. 

.. _intro-overview-item:

We need to write a Spider which visits some initial url
(in our case https://github.com/trending?l=python), extracts links, 
follows them by issuing GET requests and extracts data from repository pages.

.. highlight:: html

Extract and follow links
========================

Let's start with link extraction. If we open our browser developer tools 
and look at page source we'll see that all URLs leading to repositories 
are wrapped in html that looks like this::

    <h3 class="repo-list-name">
        <a href="/honnibal/spaCy">
        .....
        </a> 
    </h3>

.. highlight:: none

We'll use `XPath`_ for selecting proper links to repositories. In our case the
xpath will look like this::

    //h3[@class='repo-list-name']/a/@href

.. highlight:: python

To create a Spider that is going to process initial url, extract and follow
linkes that we are interested in we need to write following piece of code::

    from urlparse import urljoin

    from scrapy import Spider
    from scrapy.http import Request


    class GithubSpider(Spider):
        name = 'github_spider'
        start_urls = [
            "https://github.com/trending?l=python"
        ]

        def parse(self, response):
            links_xpath = "//h3[@class='repo-list-name']/a/@href"
            # extract links
            links = response.xpath(links_xpath).extract()[:4]
            for link in links:
                # convert relative urls to absolute
                url = urljoin(response.url, link)
                # send GET request to url
                yield Request(url)


To run this spider you need to save the code in file 'github_spider.py' (or any
name you want, name of file does not have to match name of spider) and run::

    scrapy runspider github_spider.py

This command will start spider, enable Scrapy built in middleware including CookieMiddleware, 
UserAgentMiddleware, RetryMiddleware and more. Spider will issue GET request to all
start_urls (in our case just one) with spider's 'parse' method as callback.
Parse method will execute after response arrives,
it will extract links from response and issue 4 asynchronous GET requests to 
Github repositories.  

Note that you only need 18 lines of codes (even 11 lines excluding imports)
to create asynchrounous web client that is able to do all things that normal browser does (all except
rendering JavaScript and CSS of course). It will manage cookie for you, 
it will add proper user agent, handle redirects, retry on error conditions and 
more. 

Define models and extract data
==============================

Now that we have a spider that follows links from 'Trending Repositories' 
page we can actually extract some data from repos.

First we need to define the data we want to scrape. In Scrapy, this is
done through :ref:`Scrapy Items <topics-items>`. Our items will represent
Python repositories::

    import scrapy import Item, Field

    class RepoItem(Item):
        url = Field()
        name = Field()
        forks = Field()

.. highlight:: html

Let's check how we can extract data from each repo page. 
If we look at example repo page (https://github.com/scrapy/scrapy)
we can see that repository name is contained
inside an ``<a>`` element with css class ``js-current-repository``::

    <a data-pjax="#js-repo-pjax-container" class="js-current-repository" href="/scrapy/scrapy">scrapy</a>

.. highlight:: none

To match repository name we need following xpath:::

    //a[@class='js-current-repository']/text()

.. highlight:: html

For more information about XPath see the `XPath reference`_.

If we look up number of forks in HTML source we will quickly notice 
they hidden inside ``a`` element:::

    <a class="social-count" href="/scrapy/scrapy/network">
        2,018
    </a>

.. highlight:: python

Proper xpath to match this HTML would be:::

    //a[@class='social-count']//text()

At this point we have all we need to update our
spider so that it will gather data from each repo. First we need to add
item definitions to spider script, then we need to add new
method to spider. Our new method will be called ``parse_repo`` and it is 
going to be executed as callback for requests issued from ``parse``. 
In this new method we will extract our data and return it.

Here's the spider code::

    from urlparse import urljoin

    from scrapy import Spider, Item, Field
    from scrapy.http import Request
    from scrapy.contrib.loader import ItemLoader


    class RepoItem(Item):
        url = Field()
        name = Field()
        forks = Field()


    class GithubSpider(Spider):
        name = 'github_spider'
        start_urls = [
            "https://github.com/trending?l=python"
        ]

        def parse(self, response):
            links_xpath = "//h3[@class='repo-list-name']/a/@href"
            links = response.xpath(links_xpath).extract()[:4]
            for link in links:
                url = urljoin(response.url, link)
                yield Request(url, callback=self.parse_repo)

        def parse_repo(self, response):
            loader = ItemLoader(item=RepoItem(), selector=response)
            loader.add_value("url", response.url)
            loader.add_xpath("name", "//a[@class='js-current-repository']/text()")
            loader.add_xpath("forks", "//a[@class='social-count']//text()")
            yield loader.load_item()

We used :ref:`Item Loaders <topics-loaders>` to make data extraction easier. 
With item loaders you only need to specify xpath or css path and loader will extract
data for you.

Run your spider
===============

Finally let's run the spider to crawl the site and save data as JSON in file named
``scraped_data.json``::

    scrapy runspider github_spider.py -o scraped_data.json

This uses :ref:`feed exports <topics-feed-exports>` to generate the JSON file.
You can easily change the export format (XML or CSV, for example) or the
storage backend (FTP or `Amazon S3`_, for example).

You can also write an :ref:`item pipeline <topics-item-pipeline>` to store the
items in a database very easily.

If you check the ``scraped_data.json`` file after the process finishes, you'll
see that scraped items are there::

    {
        url: [
            "https://github.com/sdiehl/numpile"
        ],
        forks: [
            " 13 "
        ],
        name: [
            "numpile"
        ]
    },

You'll notice that all field values are actually lists. 
This is because :ref:`selectors <topics-selectors>` return lists. 
You may want to store single values, or perform some additional 
parsing/cleansing to the values. 

That's what :ref:`Item Loaders <topics-loaders>` are for.

.. _topics-whatelse:

What else?
==========

You've seen how to extract and store items from a website using Scrapy, but
this is just the surface. Scrapy provides a lot of powerful features for making
scraping easy and efficient, such as:

* Built-in support for :ref:`selecting and extracting <topics-selectors>` data
  from HTML and XML sources

* Built-in support for cleaning and sanitizing the scraped data using a
  collection of reusable filters (called :ref:`Item Loaders <topics-loaders>`)
  shared between all the spiders.

* Built-in support for :ref:`generating feed exports <topics-feed-exports>` in
  multiple formats (JSON, CSV, XML) and storing them in multiple backends (FTP,
  S3, local filesystem)

* A media pipeline for :ref:`automatically downloading images <topics-images>`
  (or any other media) associated with the scraped items

* Support for :ref:`extending Scrapy <extending-scrapy>` by plugging
  your own functionality using :ref:`signals <topics-signals>` and a
  well-defined API (middlewares, :ref:`extensions <topics-extensions>`, and
  :ref:`pipelines <topics-item-pipeline>`).

* Wide range of built-in middlewares and extensions for:

  * cookies and session handling
  * HTTP compression
  * HTTP authentication
  * HTTP cache
  * user-agent spoofing
  * robots.txt
  * crawl depth restriction
  * and more

* Robust encoding support and auto-detection, for dealing with foreign,
  non-standard and broken encoding declarations.

* Support for creating spiders based on pre-defined templates, to speed up
  spider creation and make their code more consistent on large projects. See
  :command:`genspider` command for more details.

* Extensible :ref:`stats collection <topics-stats>` for multiple spider
  metrics, useful for monitoring the performance of your spiders and detecting
  when they get broken

* An :ref:`Interactive shell console <topics-shell>` for trying XPaths, very
  useful for writing and debugging your spiders

* A :ref:`System service <topics-scrapyd>` designed to ease the deployment and
  run of your spiders in production.

* A :ref:`Telnet console <topics-telnetconsole>` for hooking into a Python
  console running inside your Scrapy process, to introspect and debug your
  crawler

* :ref:`Logging <topics-logging>` facility that you can hook on to for catching
  errors during the scraping process.

* Support for crawling based on URLs discovered through `Sitemaps`_

* A caching DNS resolver

What's next?
============

The next obvious steps are for you to `download Scrapy`_, read :ref:`the
tutorial <intro-tutorial>` and join `the community`_. 

.. _download Scrapy: http://scrapy.org/download/
.. _the community: http://scrapy.org/community/
.. _screen scraping: http://en.wikipedia.org/wiki/Screen_scraping
.. _web scraping: http://en.wikipedia.org/wiki/Web_scraping
.. _Amazon Associates Web Services: http://aws.amazon.com/associates/
.. _XPath: http://www.w3.org/TR/xpath
.. _XPath reference: http://www.w3.org/TR/xpath
.. _Amazon S3: http://aws.amazon.com/s3/
.. _Sitemaps: http://www.sitemaps.org
