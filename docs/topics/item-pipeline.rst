.. _topics-item-pipeline:

=============
Item Pipeline
=============

After an item has been scraped by a spider, it is sent to the Item Pipeline
which process it through several components that are executed sequentially.

Each item pipeline component (sometimes referred as just "Item Pipeline") is a
Python class that implements a simple method. They receive an Item and perform
an action over it, also deciding if the Item should continue through the
pipeline or be dropped and no longer processed.

Typical use for item pipelines are:

* cleansing HTML data
* validating scraped data (checking that the items contain certain fields)
* checking for duplicates (and dropping them)
* storing the scraped item in a database


Writing your own item pipeline
==============================

Writing your own item pipeline is easy. Each item pipeline component is a
single Python class that must implement the following method:

.. method:: process_item(item, spider)

   This method is called for every item pipeline component and must either return
   a :class:`~scrapy.item.Item` (or any descendant class) object or raise a
   :exc:`~scrapy.exceptions.DropItem` exception. Dropped items are no longer
   processed by further pipeline components.

   :param item: the item scraped
   :type item: :class:`~scrapy.item.Item` object

   :param spider: the spider which scraped the item
   :type spider: :class:`~scrapy.spider.BaseSpider` object

Additionally, they may also implement the following methods:

.. method:: open_spider(spider)

   This method is called when the spider is opened.

   :param spider: the spider which was opened
   :type spider: :class:`~scrapy.spider.BaseSpider` object

.. method:: close_spider(spider)

   This method is called when the spider is closed.

   :param spider: the spider which was closed
   :type spider: :class:`~scrapy.spider.BaseSpider` object


Item pipeline example
=====================

Price validation and dropping items with no prices
--------------------------------------------------

Let's take a look at the following hypothetic pipeline that adjusts the ``price``
attribute for those items that do not include VAT (``price_excludes_vat``
attribute), and drops those items which don't contain a price::

    from scrapy.exceptions import DropItem

    class PricePipeline(object):

        vat_factor = 1.15

        def process_item(self, item, spider):
            if item['price']:
                if item['price_excludes_vat']:
                    item['price'] = item['price'] * self.vat_factor
                return item
            else:
                raise DropItem("Missing price in %s" % item)


Write items to a JSON file
--------------------------

The following pipeline stores all scraped items (from all spiders) into a a
single ``items.jl`` file, containing one item per line serialized in JSON
format::

   import json

   class JsonWriterPipeline(object):

       def __init__(self):
           self.file = open('items.jl', 'wb')

       def process_item(self, item, spider):
           line = json.dumps(dict(item)) + "\n"
           self.file.write(line)
           return item

.. note:: The purpose of JsonWriterPipeline is just to introduce how to write
   item pipelines. If you really want to store all scraped items into a JSON
   file you should use the :ref:`Feed exports <topics-feed-exports>`.

Duplicates filter
-----------------

A filter that looks for duplicate items, and drops those items that were
already processed. Let say that our items have an unique id, but our spider
returns multiples items with the same id::


    from scrapy import signals
    from scrapy.exceptions import DropItem

    class DuplicatesPipeline(object):

        def __init__(self):
            self.ids_seen = set()

        def process_item(self, item, spider):
            if item['id'] in self.ids_seen:
                raise DropItem("Duplicate item found: %s" % item)
            else:
                self.ids_seen.add(item['id'])
                return item


Activating an Item Pipeline component
=====================================

To activate an Item Pipeline component you must add its class to the
:setting:`ITEM_PIPELINES` list, like in the following example::

   ITEM_PIPELINES = [
       'myproject.pipeline.PricePipeline',
       'myproject.pipeline.JsonWriterPipeline',
   ]
