.. _topics-newitem-index:

.. _topics-newitem-scrapeditem:

=====
Items
=====

.. currentmodule:: scrapy.item

The goal of the scraping process is to obtain scraped items from scraped pages.

Basic scraped items
===================

In Scrapy the items are represented by a :class:`ScrapedItem` (almost an empty
class) or any subclass of it.

To use :class:`ScrapedItem` you simply instantiate it and use instance
attributes to store the information.

   >>> from scrapy.item import ScrapedItem
   >>> item = ScrapedItem()
   >>> item.headline = 'Headline'
   >>> item.content = 'Content'
   >>> item.published = '2009-07-08'
   >>> item
   ScrapedItem({'headline': 'Headline', 'content': 'Content', 'published': '2009-07-08'})

Or you can use your own class to represent items, just be sure it inherits from
:class:`ScrapedItem`.

.. _topics-newitem-index-item:

More advanced items
===================

.. currentmodule:: scrapy.contrib_exp.newitem

Scrapy provides :class:`Item` (a subclass of :class:`~scrapy.item.ScrapedItem`)
that works like a form with fields to store the item's data.

To use this items you first define the item's fields as class attributes::

   from scrapy.contrib_exp.newitem import Item
   from scrapy.contrib_exp.newitem import fields

   class NewsItem(Item):
       headline = fields.TextField()
       content = fields.TextField()
       published = fields.DateField()

And then you instantiate the item and assign values to its fields, which will be
converted to the expected Python types depending of their class::

   >>> item = NewsItem()
   >>> item['headline'] = u'Headline'
   >>> item['content'] = u'Content'
   >>> item['published'] = '2009-07-08'
   >>> item
   NewsItem(headline=u'Headline', content=u'Content', published=datetime.date(2009, 7, 8))

Using this may seen complicated at first, but gives you much power over scraped
data, like :ref:`topics-newitem-index-defaults`,
:ref:`topics-newitem-adaptors`, etc.

.. _topics-newitem-index-defaults:

Default values for fields
-------------------------

Each field accepts a ``default`` argument, that sets the default value of the
field.

Fields which contain a default value will always return that value when not
set, while fields which don't contain a default value will raise ``KeyError``,
you can use :meth:`Item.get` method to avoid this.

.. code-block:: python

   from scrapy.contrib_exp.newitem import Item, fields

   class NewsItem(Item):
       headline = fields.TextField()
       content = fields.TextField()
       published = fields.DateField()
       author = fields.TextField(default=u'Myself')
       views = fields.IntegerField(default=0)

.. code-block:: python

   >>> item = NewsItem()
   >>> item['author']
   u'Myself'
   >>> item['views']
   0
   >>> item['headline']
   Traceback (most recent call last):
   ...
   KeyError: 'headline
   >>> item.get('headline') is None
   True

