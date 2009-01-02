=============
Item Pipeline
=============

After an item has been scraped by a spider it is sent to the Item Pipeline
which process it through several stages that are executed sequentially.

Item pipeline are usually implemented on each project. Typical usage for item
pipelines are: 

 * HTML cleansing
 * validation
 * persistence (storing the scraped item)

To implement an item pipeline you need to implement a class which contains a
``process_item`` method. That method must either return a ScrapedItem (or any
descendant class) object or raise a :exception:`DropItem` exception. Dropped
items are no longer processed by further pipeline stages.

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

        def open_domain(self, domain):
            pass

        def close_domains(self, domain):
            pass


You may also noticed the two other methods that a item pipeline class can
contain: ``open_domain`` which is called when the domain for that spider is
open, and ``close_domain`` which is called when it's closed.

