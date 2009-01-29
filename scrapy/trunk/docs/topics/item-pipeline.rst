.. _topics-item-pipeline:

=============
Item Pipeline
=============

After an item has been scraped by a spider it is sent to the Item Pipeline
which process it through several components that are executed sequentially.

Item pipeline are usually implemented on each project. Typical usage for item
pipelines are: 

 * HTML cleansing
 * validation
 * persistence (storing the scraped item)


Writing your own item pipeline
==============================

Writing your own item pipeline is easy. Each item pipeline component is a
single Python class that must define the following method:

.. method:: process_item(domain, item)

``domain`` is a string with the domain of the spider which scraped the item

``item`` is a :class:`scrapy.item.ScrapedItem` with the item scraped

This method is called for every item pipeline component and must either return
a ScrapedItem (or any descendant class) object or raise a :exception:`DropItem`
exception. Dropped items are no longer processed by further pipeline
components.


Item pipeline example
=====================

Let's take a look at following hypotetic pipeline that adjusts the ``price``
attribute for those items that do not include VAT (``price_excludes_vat``
attribute), and drops those items which don't contain a price::

    from scrapy.core.exceptions import DropItem

    class PricePipeline(object):

        vat_factor = 1.15

        def process_item(self, domain, item):
            if item.price:
                if item.price_excludes_vat:
                    item.price = item.price * self.vat_factor
                return item
            else:
                raise DropItem("Missing price in %s" % item)


Item pipeline example with resources per domain
===============================================

Sometimes you need to keep resources about the items processed grouped per
domain, and delete those resource when a domain finish.

An example is a filter that looks for duplicate items, and drops those items
that were already processed. Let say that our items has an unique id, but our
spider returns multiples items with the same id::


    from pydispatch import dispatcher
    from scrapy.core import signals
    from scrapy.core.exceptions import DropItem

    class DuplicatesPipeline(object):
        def __init__(self):
            self.domaininfo = {}
            dispatcher.connect(self.domain_open, signals.domain_open)
            dispatcher.connect(self.domain_closed, signals.domain_closed)

        def domain_open(self, domain):
            self.duplicates[domain] = set()

        def domain_closed(self, domain):
            del self.duplicates[domain]

        def process_item(self, domain, item):
            if item.id in self.duplicates[domain]:
                raise DropItem("Duplicate item found: %s" % item)
            else:
                self.duplicates[domain].add(item.id)
                return item
