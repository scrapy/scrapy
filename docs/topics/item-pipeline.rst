.. _topics-item-pipeline:

=============
Item Pipeline
=============

After an item has been scraped by a spider, it is sent to the Item Pipeline.

A pipeline component only runs if it is registered in the
:setting:`ITEM_PIPELINES` setting in ``settings.py``. Defining the class
alone has no effect.

Each item pipeline component (sometimes referred as just "Item Pipeline") is a
Python class that implements a simple method. They receive an item and perform
an action over it, also deciding if the item should continue through the
pipeline or be dropped and no longer processed.

Typical uses of item pipelines are:

* cleansing HTML data
* validating scraped data (checking that the items contain certain fields)
* checking for duplicates (and dropping them)
* storing the scraped item in a database

Writing your own item pipeline
==============================

Each item pipeline is a :ref:`component <topics-components>` that must
implement the following method:

.. method:: process_item(self, item)

   This method is called for every item pipeline component.

   `item` is an :ref:`item object <item-types>`, see
   :ref:`supporting-item-types`.

   :meth:`process_item` must either return an :ref:`item object <item-types>`
   or raise a :exc:`~scrapy.exceptions.DropItem` exception.

   Dropped items are no longer processed by further pipeline components.

   :param item: the scraped item
   :type item: :ref:`item object <item-types>`

Additionally, they may also implement the following methods:

.. method:: open_spider(self)

   This method is called when the spider is opened.

.. method:: close_spider(self)

   This method is called when the spider is closed.

Any of these methods may be defined as a coroutine function (``async def``).


Item pipeline example
=====================

Price validation and dropping items with no prices
--------------------------------------------------

Let's take a look at the following hypothetical pipeline that adjusts the
``price`` attribute for those items that do not include VAT
(``price_excludes_vat`` attribute), and drops those items which don't
contain a price:

.. code-block:: python

    from itemadapter import ItemAdapter
    from scrapy.exceptions import DropItem


    class PricePipeline:
        vat_factor = 1.15

        def process_item(self, item):
            adapter = ItemAdapter(item)
            if adapter.get("price"):
                if adapter.get("price_excludes_vat"):
                    adapter["price"] = adapter["price"] * self.vat_factor
                return item
            else:
                raise DropItem("Missing price")


Write items to a JSON lines file
--------------------------------

The following pipeline stores all scraped items (from all spiders) into a
single ``items.jsonl`` file, containing one item per line serialized in JSON
format:

.. code-block:: python

   import json

   from itemadapter import ItemAdapter


   class JsonWriterPipeline:
       def open_spider(self):
           self.file = open("items.jsonl", "w")

       def close_spider(self):
           self.file.close()

       def process_item(self, item):
           line = json.dumps(ItemAdapter(item).asdict()) + "\n"
           self.file.write(line)
           return item

.. note:: The purpose of JsonWriterPipeline is just to introduce how to write
   item pipelines. If you really want to store all scraped items into a JSON
   file you should use the :ref:`Feed exports <topics-feed-exports>`.

Write items to MongoDB
----------------------

In this example we'll write items to MongoDB_ using pymongo_.
MongoDB address and database name are specified in Scrapy settings;
MongoDB collection is named after item class.

The main point of this example is to show how to :ref:`get the crawler
<from-crawler>` and how to clean up the resources properly.

.. skip: next
.. code-block:: python

    import pymongo
    from itemadapter import ItemAdapter


    class MongoPipeline:
        collection_name = "scrapy_items"

        def __init__(self, mongo_uri, mongo_db):
            self.mongo_uri = mongo_uri
            self.mongo_db = mongo_db

        @classmethod
        def from_crawler(cls, crawler):
            return cls(
                mongo_uri=crawler.settings.get("MONGO_URI"),
                mongo_db=crawler.settings.get("MONGO_DATABASE", "items"),
            )

        def open_spider(self):
            self.client = pymongo.MongoClient(self.mongo_uri)
            self.db = self.client[self.mongo_db]

        def close_spider(self):
            self.client.close()

        def process_item(self, item):
            self.db[self.collection_name].insert_one(ItemAdapter(item).asdict())
            return item

.. _MongoDB: https://www.mongodb.com/
.. _pymongo: https://pymongo.readthedocs.io/en/stable/


.. _ScreenshotPipeline:

Take screenshot of item
-----------------------

This example demonstrates how to use :doc:`coroutine syntax <coroutines>` in
the :meth:`process_item` method.

This item pipeline makes a request to a locally-running instance of Splash_ to
render a screenshot of the item URL. After the request response is downloaded,
the item pipeline saves the screenshot to a file and adds the filename to the
item.

.. code-block:: python

    import hashlib
    from pathlib import Path
    from urllib.parse import quote

    import scrapy
    from itemadapter import ItemAdapter
    from scrapy.http.request import NO_CALLBACK


    class ScreenshotPipeline:
        """Pipeline that uses Splash to render screenshot of
        every Scrapy item."""

        SPLASH_URL = "http://localhost:8050/render.png?url={}"

        def __init__(self, crawler):
            self.crawler = crawler

        @classmethod
        def from_crawler(cls, crawler):
            return cls(crawler)

        async def process_item(self, item):
            adapter = ItemAdapter(item)
            encoded_item_url = quote(adapter["url"])
            screenshot_url = self.SPLASH_URL.format(encoded_item_url)
            request = scrapy.Request(screenshot_url, callback=NO_CALLBACK)
            response = await self.crawler.engine.download_async(request)

            if response.status != 200:
                # Error happened, return item.
                return item

            # Save screenshot to file, filename will be hash of url.
            url = adapter["url"]
            url_hash = hashlib.md5(url.encode("utf8")).hexdigest()
            filename = f"{url_hash}.png"
            Path(filename).write_bytes(response.body)

            # Store filename in item.
            adapter["screenshot_filename"] = filename
            return item

.. _Splash: https://splash.readthedocs.io/en/stable/

Duplicates filter
-----------------

A filter that looks for duplicate items, and drops those items that were
already processed. Let's say that our items have a unique id, but our spider
returns multiples items with the same id:

.. code-block:: python

    from itemadapter import ItemAdapter
    from scrapy.exceptions import DropItem


    class DuplicatesPipeline:
        def __init__(self):
            self.ids_seen = set()

        def process_item(self, item):
            adapter = ItemAdapter(item)
            if adapter["id"] in self.ids_seen:
                raise DropItem(f"Item ID already seen: {adapter['id']}")
            else:
                self.ids_seen.add(adapter["id"])
                return item

.. _topics-item-pipeline-minimal-example:

End-to-end example
==================

The following shows a complete integration — a spider that yields an item,
a pipeline that validates it, and the settings that wire them together.

Each yielded item is processed by the enabled pipelines in order of their priority values defined in :setting:`ITEM_PIPELINES`.

``myproject/items.py``::

    import scrapy

    class BookItem(scrapy.Item):
        title = scrapy.Field()
        price = scrapy.Field()

``myproject/spiders/books_spider.py``::

    import scrapy
    from myproject.items import BookItem

    class BooksSpider(scrapy.Spider):
        name = "books"
        start_urls = ["https://books.toscrape.com"]

        def parse(self, response):
            for book in response.css("article.product_pod"):
                item = BookItem()
                item["title"] = book.css("h3 a::attr(title)").get()
                item["price"] = book.css(".price_color::text").get()
                yield item

``myproject/pipelines.py``::

    from itemadapter import ItemAdapter
    from scrapy.exceptions import DropItem

    class PriceValidationPipeline:
        def process_item(self, item, spider):
            adapter = ItemAdapter(item)
            if not adapter.get("price"):
                raise DropItem(f"Missing price in: {item!r}")
            return item

``myproject/settings.py``::

    ITEM_PIPELINES = {
        "myproject.pipelines.PriceValidationPipeline": 100,
    }

Running ``scrapy crawl books`` will scrape items and pass each item through
``PriceValidationPipeline`` before any further processing.

Activating an Item Pipeline component
=====================================

To activate an Item Pipeline component you must add its class to the
:setting:`ITEM_PIPELINES` setting, like in the following example:

.. code-block:: python

   ITEM_PIPELINES = {
       "myproject.pipelines.PricePipeline": 300,
       "myproject.pipelines.JsonWriterPipeline": 800,
   }

The integer values you assign to classes in this setting determine the
order in which they run: items go through from lower valued to higher
valued classes. It's customary to define these numbers in the 0-1000 range.

.. _topics-item-pipeline-pitfalls:

Common pitfalls
===============

Not returning the item
----------------------

:meth:`process_item` must either return an item object or raise
:exc:`~scrapy.exceptions.DropItem`. Returning ``None`` silently stops
the item from reaching subsequent pipeline components:

.. code-block:: python

    # Wrong — returns None implicitly
    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        adapter["price"] = float(adapter["price"].strip("£"))

    # Correct
    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        adapter["price"] = float(adapter["price"].strip("£"))
        return item

Pipeline not running
--------------------

If a pipeline class is not being called, first check the Scrapy log at
startup — enabled pipelines are listed there, which makes it easy to
confirm whether your pipeline was picked up at all.

A common cause is that the pipeline is not listed in
:setting:`ITEM_PIPELINES` in ``settings.py``. Another is that a
higher-priority :setting:`ITEM_PIPELINES` definition elsewhere — for
example in a spider's ``custom_settings``, or in a cloud service
configuration — is silently overriding your ``settings.py`` value.
Accidentally defining :setting:`ITEM_PIPELINES` twice in ``settings.py``
is also a known source of this problem; static analysis tools like
``ruff`` can help catch it.

Opening resources in ``__init__``
----------------------------------

Use :meth:`open_spider` to open database connections or file handles,
and :meth:`close_spider` to release them. This ties the resource
lifecycle to the crawl, not to class instantiation:

.. code-block:: python

    class DatabasePipeline:
        def open_spider(self, spider):
            self.conn = db.connect()

        def close_spider(self, spider):
            self.conn.close()

        def process_item(self, item, spider):
            self.conn.insert(ItemAdapter(item).asdict())
            return item