.. _topics-newitem:

=========
New Items
=========

The goal of the scraping process is to obtain scraped items from scraped pages.

Basic scraped items
===================

In Scrapy the items are represented by a :class:`~scrapy.item.ScrapedItem`
(almost an empty class) or any subclass of it.

To use :class:`~scrapy.item.ScrapedItem` you simply instantiate it and use
instance attributes to store the information.

   >>> from scrapy.item import ScrapedItem
   >>> item = ScrapedItem()
   >>> item.headline = 'Headline'
   >>> item.content = 'Content'
   >>> item.published = '2009-07-08'
   >>> item
   ScrapedItem({'headline': 'Headline', 'content': 'Content', 'published': '2009-07-08'})

Or you can use your own class to represent items, just be sure it inherits from
:class:`~scrapy.item.ScrapedItem`.

More advanced items
===================

.. class:: scrapy.contrib_exp.newitem.Item(ScrapedItem)

Scrapy provides :class:`~scrapy.contrib_exp.newitem.Item` (a subclass of
:class:`~scrapy.item.ScrapedItem`) that works like a form with fields to store
the item's data.

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
   >>> item.headline = u'Headline'
   >>> item.content = u'Content'
   >>> item.published = '2009-07-08'
   >>> item
   NewsItem({'headline': u'Headline', 'content': u'Content', 'published': datetime.date(2009, 7, 8)})

Each field accepts a ``default`` argument, that sets the default value of the field.

You can see the built-in field types in the :ref:`ref-newitem-fields`.

Using this may seen complicated at first, but gives you much power over scraped
data, like assigning defaults for fields that are not present in some pages,
:ref:`topic-newitem-adaptors`, etc.

.. _topic-newitem-adaptors:

=============
Item Adaptors
=============

.. class:: scrapy.contrib_exp.newitem.adaptors.ItemAdaptor

As you probably want to scrape the same kind of Items from many sources
(different websites, RSS feeds, etc.), Scrapy implements ItemAdaptors, they
allow you to adapt chunks of HTML or XML (selected using Selectors) to the
expected format of your Item fields.

An ItemAdaptor acts like a wrapper of an Item, you define an ItemAdaptor class,
set the Item class to wrap and assign a set of functions (adaptor functions) to be called when you assign a value to a field.

Here's an example of an ItemAdaptor for our previously created Item::

   class NewsAdaptor(ItemAdaptor):
       item_class = NewsItem

       url = adaptor(extract, remove_tags(), unquote(), strip)
       headline = adaptor(extract, remove_tags(), unquote(), strip)
       summary = adaptor(extract, remove_tags(), unquote(), strip)
       content = adaptor(extract, remove_tags(), unquote(), strip)

How do we use it? Let's see it in action in a Spider::

   def parse_newspage(self, response):
       xhs = HtmlXPathSelector(response)
       i = NewsAdaptor(response)

       i.url = response.url
       i.headline = xhs.x('//h1[@class="headline"]')
       i.summary = xhs.x('//div[@class="summary"]')
       i.content = xhs.x('//div[@id="body"]')
       # we intentionally left published out of the example, see below for site
       # specific adaptors
       return [i]

What happens underneath?

When we assign a value to a ItemAdaptor field it passes for the chain of
functions defined previously in it's class, in this case, the value gets
extracted (note that we assign directly the value obtained from the Selector),
then tags will be removed, then the result will be unquoted, stripped and
finally assigned to the Item Field.

This final assignment is done in an internal instance of the Item on the
ItemAdaptor, that's why we can return an ItemAdaptor instead of an Item and
Scrapy will know how to extract the item from it.

A Item can have as many ItemAdaptors as you want it generally depends on how
many sources and formats are you scraping from.

ItemAdaptor inheritance
=======================

As we said before you generally want an ItemAdaptor for each different source of
data and maybe some for specific sites, inheritance make this really easy, let's
see an example of adapting HTML and XML::

   class NewsAdaptor(ItemAdaptor):
       item_class = NewsItem


   class HtmlNewsAdaptor(NewsAdaptor):
       url = adaptor(extract, remove_tags(), unquote(), strip)
       headline = adaptor(extract, remove_tags(), unquote(), strip)
       summary = adaptor(extract, remove_tags(), unquote(), strip)
       content = adaptor(extract, remove_tags(), unquote(), strip)
       published = adaptor(extract, remove_tags(), unquote(), strip)

       
   class XmlNewsAdaptor(HtmlNewsAdaptor):
       url = adaptor(extract, remove_root, strip)
       headline = adaptor(extract, remove_root, strip)
       summary = adaptor(extract, remove_root, strip)
       content = adaptor(extract, remove_root, strip)
       published = adaptor(extract, remove_root, strip)


Site specific ItemAdaptors
==========================

For the moment we have covered adapting information from different sources, but
other common case is adapting information for specific sites, think for example
in our published field, it keeps the publication date of the news article.

As sites offer this information in different formats, we will have to make
custom adaptors for it, let's see an example using our Item published field::

   class SpecificSiteNewsAdaptor(HtmlNewsAdaptor):
       published = adaptor(HtmlNewsAdaptor.published, to_date('%d.%m.%Y')) 


The ``to_date`` adaptor function converts a string with the format specified in
its parameter to one in 'YYYY-mm-dd' format (the one that DateField expects).

And in this example we're appending it to the of the chain of adaptor functions
of published.

Note that ``SpecificSiteNewsAdaptor`` will inherit the field adaptations from
``HtmlNewsAdaptor``.

Let's see it in action::

   def parse_newspage(self, response):
       xhs = HtmlXPathSelector(response)
       i = SpecificSiteNewsAdaptor(response)

       i.url = response.url
       i.headline = xhs.x('//h1[@class="headline"]')
       i.summary = xhs.x('//div[@class="summary"]')
       i.content = xhs.x('//div[@id="body"]')
       i.published = xhs.x('//h1[@class="date"]').re( '\d{2}\.\d{2}\.\d{4}')
       return [i]

ItemAdaptor default_adaptor
===========================

If you look closely at the code for our ItemAdaptors you can see that we're using the same set of adaptation functions in every field.

It is common for ItemAdaptors to have a basic set of adaptor functions that will be applied to almost every Field in the Item. To avoid repeating the same code, ItemAdaptor implements the ``default_adaptor`` shortcut.

``default_adaptor`` (if set) will be called when assigning a value for an Item
Field that has no adaptor, so the process for determining what value gets assigned to an item when you assign a value to an ItemAdaptor field is as follows:

* If there's an adaptor function for this field its called before assigning the
  value to the item. 
* If no adaptor function if set and default_adaptor is, the value passes for 
  ``default_adaptor`` before being assigned.
* If no adaptor is defined for that field and no ``default_adaptor`` is set, the value is assigned directly.
