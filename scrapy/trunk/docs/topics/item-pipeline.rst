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

.. method:: process_item(request, spider)

``request`` is a Request object
``spider`` is a BaseSpider object

This method is called for every item pipeline component and must either return
a ScrapedItem (or any descendant class) object or raise a :exception:`DropItem`
exception. Dropped items are no longer processed by further pipeline
components.


The class can also define the followin optional methods:

.. method:: open_domain(domain)

``domain`` is a string which identifies the spider opened

This method is called when a spider is opened for crawling.

.. method:: close_domain(domain)

``domain`` is a string which identifies the spider closed

This method is called when a spider is closed.


Item pipeline example
=====================

Let's take a look at following hypotetic pipeline that adjusts the ``price``
attribute for those items that do not include VAT (``price_excludes_vat``
attribute), and drops those items which don't contain a price::

    from scrapy.core.exceptions import DropItem

    class PricePipeline(object):

        vat_factor = 1.15

        def process_item(self, domain, response, item):
            if item.price:
                if item.price_excludes_vat:
                    item.price = item.price * self.vat_factor
                return item
            else:
                raise DropItem("Missing price in %s" % item)

