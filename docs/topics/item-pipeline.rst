.. _topics-item-pipeline:

=============
Item Pipeline
=============

After an item has been scraped by a spider, it is sent to the Item Pipeline
which process it through several components that are executed sequentially.

Item pipelines are usually implemented on each project. Typical usage for item
pipelines consists of:

* HTML cleansing
* validation
* persistence (storing the scraped item)


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


Activating an Item Pipeline component
=====================================

To activate an Item Pipeline component you must add its class to the
:setting:`ITEM_PIPELINES` list, like in the following example::

   ITEM_PIPELINES = [
       'myproject.pipeline.PricePipeline',
   ]

Item pipeline example with resources per spider
===============================================

Sometimes you need to keep resources about the items processed grouped per
spider, and delete those resource when a spider finishes.

An example is a filter that looks for duplicate items, and drops those items
that were already processed. Let say that our items have an unique id, but our
spider returns multiples items with the same id::


    from scrapy.xlib.pydispatch import dispatcher
    from scrapy import signals
    from scrapy.exceptions import DropItem

    class DuplicatesPipeline(object):
        def __init__(self):
            self.duplicates = {}
            dispatcher.connect(self.spider_opened, signals.spider_opened)
            dispatcher.connect(self.spider_closed, signals.spider_closed)

        def spider_opened(self, spider):
            self.duplicates[spider] = set()

        def spider_closed(self, spider):
            del self.duplicates[spider]

        def process_item(self, item, spider):
            if item['id'] in self.duplicates[spider]:
                raise DropItem("Duplicate item found: %s" % item)
            else:
                self.duplicates[spider].add(item['id'])
                return item
