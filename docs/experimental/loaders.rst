.. _topics-loader:

============
Item Loaders
============

.. module:: scrapy.newitem.loader
   :synopsis: Item Loader class

Item Loaders (or Loaders, for short) provide a convenient mechanism for
populating scraped :ref:`Items <topics-newitems>`. Even though Items can be
populated using their own dictionary-like API, the Loaders provide a much more
convenient API for populating them from a scraping process, by automating some
common tasks like parsing the raw extracted data before assigning it.

In other words, :ref:`Items <topics-newitems>` provide the *container* of
scraped data, while Loaders provide the mechanism for *populating* that
container.

Loaders are designed to provide a flexible, efficient and easy mechanism for
extending and overriding different field parsing rules (either by spider, or by
source format) without becoming a nightmare to maintain

Using Loaders to populate items
===============================

To use a Loader, you must first instantiate it. You can either instantiate it
with an Item object or without one, in which case an Item is automatically
instantiated in the Loader constructor using the Item class specified in the
:attr:`ItemLoader.default_item_class` attribute.

Then, you start adding values to the Loader, typically collecting them using
:ref:`Selectors <topics-selectors>`. You can add more than one value to the
same item field, the Loader will know how to "join" those values later using a
Reducer.

Here is a typical Loader usage in a :ref:`Spider <topics-spiders>` using the
:ref:`Product item defined in the Items chapter <topics-newitems-declaring>`.::

    from scrapy.item.loader import Loader
    from scrapy.xpath import HtmlXPathSelector
    from myproject.items import Product

    def parse(self, response):
        x = HtmlXPathSelector(response)
        l = ItemLoader(item=Product())
        l.add_value('name', x.x('//div[@class="product_name"]').extract())
        l.add_value('name', x.x('//div[@class="product_title"]').extract())
        l.add_value('price', x.x('//p[@id="price"]').extract())
        l.add_value('stock', x.x('//p[@id="stock"]').extract())
        l.add_value('last_updated', 'today')
        return l.get_item()

By looking at that code we can see the ``name`` field is being extracted from
two different XPath locations in the page:

* ``//div[@class="product_name"]``
* ``//div[@class="product_title"]``

So both XPaths are used for extracting data from the page, and the data
returned by them is collected to be assigned to the ``name`` attribute.

Afterwards, similar calls are used for ``price`` and ``stock`` fields, and
finally the ``last_update`` field is populated directly with a literal value
(``today``).

Finally, when all data is collected, the :meth:`ItemLoader.get_item` method is
called which actually populates and returns the item populated with the data
previously extracted with the ``add_value`` calls.

Expanders and Reducers
======================

A Loader is composed of one expander and reducer for each item field. The
Expander processes the extracted data as soon as it's received through the
:meth:`ItemLoader.add_value` method, and the result of the expander is collected
and kept inside the Loader. After collecting all data, the
:meth:`ItemLoader.get_item` method is called to actually populate and get the Item.
That's when the Reducers are called with the data previously collected (using
the Expanders) and the output of the Reducers are the actual values that get
assigned to the item.

Let's see an example to illustrate how Expanders and Reducers are called, for a
particular field (the same applies for any other field)::

    l = ItemLoader(Product())
    l.add_value('name', x.x(xpath1).extract()) # (1)
    l.add_value('name', x.x(xpath2).extract()) # (2)
    return l.get_item() # (3)

So what happens is:

1. Data from ``xpath1`` is extracted, and passed through the Expander of the
   ``name`` field. The output of the expander is collected and kept in the
   loader (but not yet assigned to the item).

2. Data from ``xpath2`` is extracted, and passed through the same Expander used
   in (1). The output of the expander is appended to the data collected in (1)
   (if any).

3. The data collected in (1) and (2) is passed through the Reducer of the
   ``name`` field. The output of the Reducer is the value assigned to the
   ``name`` field in the item.

Scrapy comes with one major expander built-in, the :ref:`Tree Expander
<topics-loader-tree-expander>`, and :ref:`a couple of commonly used reducers
<topics-loader-reducers>`.

Declaring Loaders
=================

Loaders are declared like Items, by using a class definition syntax. Here is an
example::

    from scrapy.newitem.loader import ItemLoader
    from scrapy.newitem.loader.expanders import TreeExpander
    from scrapy.newitem.loader.reducers import Join, TakeFirst

    class ProductLoader(ItemLoader):

        default_expander = TakeFirst()

        name_exp = TreeExpander(unicode.title)
        name_red = Join()

        price_exp = TreeExpander(unicode.strip)
        price_red = TakeFirst()

        ...

As you can see, expanders are declared using the ``_exp`` suffix while reducers
are declared using the ``_red`` suffix. And you can also declare a default
expander using the :attr:`ItemLoader.default_expander` attribute.

.. _topics-loader-args:

Item Loader arguments
=====================

The Loader arguments is a dict of arbitrary key/values which can be passed when
declaring, instantiating or using Loaders. They are used modify the behaviour
of the expanders.

For example, suppose you have a function ``parse_length`` which receives a text
value and extracts a length from it::

    def parse_length(text, loader_args):
        unit = loader_args('unit', 'm')
        # ... length parsing code goes here ...
        return parsed_length

Since it receives a ``loader_args`` the Expander will pass the currently active
loader arguments when calling it. 

There are seveal ways to pass loader arguments:

1. Passing arguments on Loader declaration::

    class ProductLoader(ItemLoader):
        length_exp = TreeExpander(parse_length, unit='cm') 

2. Passing arguments on Loader instantiation::

    l = ItemLoader(product, unit='cm')

3. Passing arguments on Loader usage::

    l.add_value('length', x.x('//div').extract(), unit='cm')

ItemLoader objects
==================

.. class:: ItemLoader([item], \**loader_args)

    Return a new Item Loader for populating the given Item. If no item is
    given, one is instantiated using the class in :attr:`default_item_class`.

    .. method:: add_value(field_name, value, \**new_loader_args)
 
        Add the given ``value`` for the given field. 
        
        The value is passed through the field expander and its output appened
        to the data collected for that field. If the field already contains
        collected data, the new data is added.

        If any keyword arguments are passed, they're used as :ref:`Loader
        arguments <topics-loader-args>` when calling the expanders.

    .. method:: replace_value(field_name, value, \**new_loader_args)

        Similar to :meth:`add_value` but replaces collected data instead of
        adding it.


    .. method:: get_item()

        Populate the item with the data collected so far, and return it.

    .. method:: get_expanded_value(field_name)

        Return the expanded data for the given field. In other words, return
        the dat collected so far for the given field, without reducing it.

    .. method:: get_reduced_value(field_name)

        Return the reduced value for the given field, without modifying the
        item.

    .. method:: get_expander(field_name)

        Return the expander for the given field.

    .. method:: get_reducer(field_name)

        Return the reducer for the given field.

    .. attribute:: default_item_class

        An Item class (or factory), used to instantiate items when not given in
        the constructor.

    .. attribute:: default_expander

        The default expander to use for those fields which don't define a
        specific expander

    .. attribute:: default_reducer

        The default reducer to use for those fields which don't define a
        specific expander

Reusing and extending Loaders
=============================

As your project grows bigger and acquires more and more spiders, maintenance
becomes a fundamental problem, specially when you have to deal with many
different parsing rules per spider, a lot of exceptions, but also want to reuse
the common cases.

Loaders are designed to ease the maintenance of parsing rules, without loosing
flexibility and, at the same time, providing a convenient mechanism for
extending and overriding them. For this reason Loaders support traditional
class inheritance for for dealing with differences of specific spiders (or
group of spiders).

Suppose, for example, that some particular site encloses their product names
between three dashes (ie. ``---Plasma TV---``) and you don't want to end up
scraping those dashes in the final product names.

Here's how you can remove those dashes by reusing and extending the default
Product Loader::

    strip_dashes = lambda x: x.strip('-')

    class SiteSpecificLoader(ProductLoader):
        name_exp = TreeExpander(ProductLoader.name_exp, strip_dashes)

Another case where extending Loaders can be very helpful is when you have
multiple source formats, for example XML and HTML. In the XML version you may
want to remove ``CDATA`` occurrences. Here's an example of how to do it::

    from myproject.utils.xml import remove_cdata

    class XmlLoader(ProductLoader):
        name_exp = TreeExpander(remove_cdata, ProductLoader.name_exp)

There are many other possible ways to extend, inherit and override your
Loaders, and different Loader hierarchies may fit better for different
projects. Scrapy only provides the mechanism, it doesn't impose any specific
organization of your Loaders collection - that's up to you and your project
needs.

Available Expanders
===================

.. _topics-loader-tree-expander:

Tree Expander
-------------

The Tree Expander is the recommended Expander to use and the only really useful
one, as the other is just an identity expander.

.. module:: scrapy.newitem.loader.expanders
   :synopsis: Expander classes to use with Item Loaders
   
.. class:: TreeExpander(\*functions, \**default_loader_arguments)

    An expander which applies the given functions consecutively, in order, to
    each value returned by the previous function.

    The algorithm consists in an ordered list of functions, each of which
    receives one value and can return zero, one or more values (as a list or
    iterable). If a function returns more than one value, the next function in
    the list will be called with each of those values, potentially returning
    more values and thus expanding the execution into different branches, which
    is why this expander is called Tree Expander.

    Each expander function can optionally receive a ``loader_args`` argument,
    which will contain the currently active loader arguments.

    The keyword arguments passed in the consturctor are used as the default
    loader arguments passed to on each expander call. This arguments can be
    overriden with specific loader arguments passed on each expander call.

IdentityExpander
----------------

.. class:: IdentityExpander

    An expander which returns the original values unchanged. It doesn't support
    any constructor arguments.

.. _topics-loader-reducers:

Available Reducers
==================

.. module:: scrapy.newitem.loader.reducers
   :synopsis: Reducer classes to use with Item Loaders

Reducers are callable objects which are called with a list of values (to be
reduced) as their first and only argument. Scrapy provides some simple,
commonly used reducers, which are described below. But you can use any function
or callable as reducer.

.. class:: TakeFirst

    Return the first non-null value from the values to reduce, so it's used for
    single-valued fields. It doesn't receive any constructor arguments.

    Example::

        name_red = TakeFirst()

.. class:: Identity

    Return the values to reduce unchanged, so it's used for multi-valued
    fields. It doesn't receive any constructor arguments.
    
    Example::

        features_red = Identity()

.. class:: Join(separator=u' ')

    Return a the values to reduce joined with the separator given in the
    constructor, which defaults to ``u' '``. 

    When using the default separator, this reducer is equivalent to the
    function: ``u' '.join``

    Examples::
        
        name_red = Join()
        name_red = Join('<br>')

