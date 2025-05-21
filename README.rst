.. image:: https://scrapy.org/img/scrapylogo.png
   :target: https://scrapy.org/

======
Scrapy
======

.. image:: https://img.shields.io/pypi/v/Scrapy.svg
   :target: https://pypi.org/pypi/Scrapy
   :alt: PyPI Version

.. image:: https://img.shields.io/pypi/pyversions/Scrapy.svg
   :target: https://pypi.org/pypi/Scrapy
   :alt: Supported Python Versions

.. image:: https://github.com/scrapy/scrapy/workflows/Ubuntu/badge.svg
   :target: https://github.com/scrapy/scrapy/actions?query=workflow%3AUbuntu
   :alt: Ubuntu

.. image:: https://github.com/scrapy/scrapy/workflows/macOS/badge.svg
   :target: https://github.com/scrapy/scrapy/actions?query=workflow%3AmacOS
   :alt: macOS

.. image:: https://github.com/scrapy/scrapy/workflows/Windows/badge.svg
   :target: https://github.com/scrapy/scrapy/actions?query=workflow%3AWindows
   :alt: Windows

.. image:: https://img.shields.io/codecov/c/github/scrapy/scrapy/master.svg
   :target: https://codecov.io/github/scrapy/scrapy?branch=master
   :alt: Coverage report

.. image:: https://anaconda.org/conda-forge/scrapy/badges/version.svg
   :target: https://anaconda.org/conda-forge/scrapy
   :alt: Conda Version

.. image:: https://deepwiki.com/badge.svg
   :target: https://deepwiki.com/scrapy/scrapy
   :alt: Ask DeepWiki


Overview
========

Scrapy is a BSD-licensed fast high-level web crawling and web scraping framework, used to
crawl websites and extract structured data from their pages. It can be used for
a wide range of purposes, from data mining to monitoring and automated testing.

Scrapy is maintained by Zyte_ (formerly Scrapinghub) and `many other
contributors`_.

.. _many other contributors: https://github.com/scrapy/scrapy/graphs/contributors
.. _Zyte: https://www.zyte.com/

Check the Scrapy homepage at https://scrapy.org for more information,
including a list of features.


Requirements
============

* Python 3.9+
* Works on Linux, Windows, macOS, BSD

Install
=======

The quick way:

.. code:: bash

    pip install scrapy

See the install section in the documentation at
https://docs.scrapy.org/en/latest/intro/install.html for more details.

Documentation
=============

Documentation is available online at https://docs.scrapy.org/ and in the ``docs``
directory.

Releases
========

You can check https://docs.scrapy.org/en/latest/news.html for the release notes.

Community (blog, twitter, mail list, IRC)
=========================================

See https://scrapy.org/community/ for details.

Contributing
============

See https://docs.scrapy.org/en/master/contributing.html for details.

Code of Conduct
---------------

Please note that this project is released with a Contributor `Code of Conduct <https://github.com/scrapy/scrapy/blob/master/CODE_OF_CONDUCT.md>`_.

By participating in this project you agree to abide by its terms.
Please report unacceptable behavior to opensource@zyte.com.

Companies using Scrapy
======================

See https://scrapy.org/companies/ for a list.

Commercial Support
==================

See https://scrapy.org/support/ for details.

scrapy-spider-metadata
======================

`scrapy-spider-metadata` is an extension for Scrapy that allows you to declare and document spider arguments in a structured way, making your spiders more discoverable and easier to use. It can automatically generate metadata for your spiders, which is useful for documentation, automation, and integration with other tools.

To use `scrapy-spider-metadata`, first install it:

.. code:: bash

    pip install scrapy-spider-metadata

Then, in your spider, you can declare arguments and their metadata using the provided decorators. Here is a rich example:

.. code:: python

    import scrapy
    from scrapy_spider_metadata import argument, SpiderMetadataMixin

    class BooksSpider(SpiderMetadataMixin, scrapy.Spider):
        name = "books"

        @argument(
            name="category",
            type=str,
            required=True,
            help="Category of books to scrape (e.g. 'fiction', 'science')."
        )
        @argument(
            name="max_pages",
            type=int,
            default=5,
            help="Maximum number of pages to crawl."
        )
        def __init__(self, category, max_pages=5, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.category = category
            self.max_pages = int(max_pages)

        def start_requests(self):
            url = f"https://example.com/books/{self.category}/"
            yield scrapy.Request(url, self.parse)

        def parse(self, response):
            # ... your parsing logic ...
            pass

With this setup, tools and users can programmatically discover the available arguments, their types, defaults, and help texts. This improves usability and maintainability for complex spiders.

For more details, see the `scrapy-spider-metadata documentation <https://github.com/scrapinghub/scrapy-spider-metadata>`_.
