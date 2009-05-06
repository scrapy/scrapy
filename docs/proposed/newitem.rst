=====
Items
=====

The goal of the scraping process is to obtain Items (aka Scraped Items) from
scraped pages.

Scrapy represent this using a model with fields for Items, much like you'll do
in an ORM.

Let's see an example::

   class NewsItem(Item):
       url = StringField()
       headline = StringField()
       summary = StringField()
       content = StringField()
       published = DateField()

Using this may seen complicated at first, but gives you much power over scraped
data, like assigning defaults for fields that are not present in some pages,
performing validation, etc.

To use Items you instantiate them and then assign values to their attributes,
they will be converted to the expected Python types depending of the field
kind::

   ni = NewsItem()
   ni.url = 'http://www.news.com/news/1'
   ni.summary = 'Summary'
   ni.content = 'Content'
   ni.published = '2009-02-28'

============
ItemAdaptors
============

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
       # we intentionally left publish out of the example, see below for site
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
many sources and formats are you scraping from.

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
custom adaptors for them, let's see an example using out Item published field::

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
       i = NewsAdaptor(response)

       i.url = response.url
       i.headline = xhs.x('//h1[@class="headline"]')
       i.summary = xhs.x('//div[@class="summary"]')
       i.content = xhs.x('//div[@id="body"]')
       i.published = xhs.x('//h1[@class="date"]').re( '\d{2}\.\d{2}\.\d{4}')
       return [i]

ItemAdaptor default_adaptor
===========================

If you look closely at the code for our ItemAdaptors you can see that we're using the same set of adaptation functions in every field.

It is common for ItemAdaptors to have a basic set of adaptor functions that will be applied to almost every Field in the Item. To help you avoid repeating the same code, ItemAdaptor implements the ``default_adaptor`` shortcut.

``default_adaptor`` (if set) will be called when assigning a value for an Item
Field that has no adaptor, so the process for determining what value gets assigned to an item when you assign a value to an ItemAdaptor field is as follows:

* If there's an adaptor function for this field its called before assigning the
  value to the item. 
* If no adaptor function if set and default_adaptor is, the value passes for 
  ``default_adaptor`` before being assigned.
* If no adaptor and no default_adaptor is set, the value is assigned directly.
