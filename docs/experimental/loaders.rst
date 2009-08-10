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
:attr:`Loader.default_item_class` attribute.

Then, you start adding values to the Loader, typically collecting them using
:ref:`Selectors <topics-selectors>`. You can add more than one value to the
same item field, the Loader will know how to "join" those values later using a
Reducer.

Here is a typical Loader usage in a :ref:`Spider <topics-spiders>`, using the
:ref:`Product item <topics-newitems-declaring>` declared in the :ref:`Items
section <topics-newitems>`::

    from scrapy.item.loader import XPathLoader
    from scrapy.xpath import HtmlXPathSelector
    from myproject.items import Product

    def parse(self, response):
        l = XPathLoader(item=Product(), response=response)
        l.add_xpath('name', '//div[@class="product_name"]')
        l.add_xpath('name', '//div[@class="product_title"]')
        l.add_xpath('price', '//p[@id="price"]')
        l.add_xpath('stock', '//p[@id="stock"]')
        l.add_value('last_updated', 'today') # you can also use literal values
        return l.get_item()

By quickly looking at that code we can see the ``name`` field is being
extracted from two different XPath locations in the page:

1. ``//div[@class="product_name"]``
2. ``//div[@class="product_title"]``

In other words, data is being collected by extracting it from two XPath
locations, using the :meth:`~XPathLoader.add_xpath` method. This is the data
that will be assigned to the ``name`` field later.

Afterwards, similar calls are used for ``price`` and ``stock`` fields, and
finally the ``last_update`` field is populated directly with a literal value
(``today``) using a different method: :meth:`~Loader.add_value`.

Finally, when all data is collected, the :meth:`Loader.get_item` method is
called which actually populates and returns the item populated with the data
previously extracted and collected with the :meth:`~XPathLoader.add_xpath` and
:meth:`~Loader.add_value` calls.

.. _topics-loader-expred:

Expanders and Reducers
======================

A Loader is composed of one expander and one reducer for each (item) field. The
Expander processes the extracted data as soon as it's received (through the
:meth:`~XPathLoader.add_xpath` or :meth:`~Loader.add_value` methods) and the
result of the expander is collected and kept inside the Loader. After
collecting all data, the :meth:`Loader.get_item` method is called to actually
populate and get the :class:`~scrapy.newitem.Item` object.  That's when the
Reducers are called with the data previously collected (using the Expanders)
and the output of the Reducers are the actual values that get assigned to the
item.

Let's see an example to illustrate how Expanders and Reducers are called, for a
particular field (the same applies for any other field)::

    l = XPathLoader(Product(), some_selector)
    l.add_xpath('name', xpath1) # (1)
    l.add_xpath('name', xpath2) # (2)
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

    from scrapy.newitem.loader import Loader
    from scrapy.newitem.loader.expanders import TreeExpander
    from scrapy.newitem.loader.reducers import Join, TakeFirst

    class ProductLoader(Loader):

        default_expander = TakeFirst()

        name_exp = TreeExpander(unicode.title)
        name_red = Join()

        price_exp = TreeExpander(unicode.strip)
        price_red = TakeFirst()

        ...

As you can see, expanders are declared using the ``_exp`` suffix while reducers
are declared using the ``_red`` suffix. And you can also declare a default
expander using the :attr:`Loader.default_expander` attribute.

.. _topics-loader-expred-declaring:

Declaring Extenders and Reducers
================================

As seen in the previous section, extenders and reducers can be declared in the
Loader definition, and it's very common to declare expanders this way. However,
there is one more place where you can specify the exanders and reducers to use:
in the :ref:`Item Field <topics-newitem-fields` metadata. Here is an example::

    from scrapy.newitem import Item, Field
    from scrapy.newitem.loader.expanders import TreeExpander
    from scrapy.newitem.loader.reducers import Join, TakeFirst

    from scrapy.utils.markup import remove_entities
    from myprojct.utils import filter_prices

    class Product(Item):
        name = Field(
            expander=TreeExpander(remove_entities),
            reducer=Join(),
        )
        price = Field(
            default=0,
            expander=TreeExpander(remove_entities, filter_prices),
            reducer=TakeFirst(),
        )

The precendece order, for both expander and reducer declarations, is as
follows:

1. Loader field-specific attributes: ``field_exp`` and ``field_red`` (more
   precedence)
2. Field metadata (``expander`` and ``reducer`` key)
3. Loader defaults: :meth:`Loader.default_expander` and
   :meth:`Loader.default_reducer` (less precedence)

See also: :ref:`topics-loader-extending`.

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
Loader arguments when calling it.

There are seveal ways to pass Loader arguments:

1. Passing arguments on Loader declaration::

    class ProductLoader(Loader):
        length_exp = TreeExpander(parse_length, unit='cm')

2. Passing arguments on Loader instantiation::

    l = Loader(product, unit='cm')

3. Passing arguments on Loader usage::

    l.add_xpath('length', '//div', unit='cm')

Loader objects
==============

.. class:: Loader([item], \**loader_args)

    Return a new Item Loader for populating the given Item. If no item is
    given, one is instantiated using the class in :attr:`default_item_class`.

    .. method:: add_value(field_name, value, \**new_loader_args)

        Add the given ``value`` for the given field.

        The value is passed through the :ref:`field expander
        <topics-loader-expred>` and its output appened to the data collected
        for that field. If the field already contains collected data, the new
        data is added.

        If any keyword arguments are passed, they're used as :ref:`Loader
        arguments <topics-loader-args>` when calling the expanders.

        Examples::

            loader.add_value('name', u'Color TV')
            loader.add_value('colours', [u'white', u'blue'])
            loader.add_value('length', u'100', default_unit='cm')

    .. method:: replace_value(field_name, value, \**new_loader_args)

        Similar to :meth:`add_value` but replaces collected data instead of
        adding it.


    .. method:: get_item()

        Populate the item with the data collected so far, and return it. The
        data collected is first passed through the :ref:`field reducers
        <topics-loader-expred>` to get the final value to assign to each item
        field.

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

.. class:: XPathLoader([item, selector, response], \**loader_args)

    The :class:`XPathLoader` class extends the :class:`Loader` class providing
    more convenient mechanisms for extracting data from web pages using
    :ref:`XPath selectors <topics-selectors>`.

    :class:`XPathLoader` objects accept two more additional parameters in their
    constructors:

    :param selector: The selector to extract data from, when using the
        :meth:`add_xpath` or :meth:`replace_xpath` method.
    :type selector: :class:`~scrapy.xpath.XPathSelector` object

    :param response: The response used to construct the selector using the
        :attr:`default_selector_class`, unless the selector argument is given,
        in which case this argument is ignored.
    :type response: :class:`~scrapy.http.Response` object

    .. method:: add_xpath(field_name, xpath, \**new_loader_args)

        Similar to :meth:`Loader.add_value` but receives an XPath instead of a
        value, which is used to extract a list of unicode strings from the
        selector associated with this :class:`XPathLoader`.

        Example::

            loader.add_xpath('name', '//p[@class="product-name"]')

    .. method:: replace_xpath(field_name, xpath, \**new_loader_args)

        Similar to :meth:`add_xpath` but replaces collected data instead of
        adding it.

    .. attribute:: default_selector_class

        The class used to construct the selector, if only a response is given
        in the constructor

.. _topics-loader-extending:

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

And that's how you typically extend expanders.

As for reducers, it is more common to declare them in the field metadata, as
they usually depend only on the field and not on each specific site parsing
rule (as expanders do). See also: :ref:`topics-loader-expred-declaring`.

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
    which will contain the currently active :ref:`Loader arguments
    <topics-loader-args>`.

    The keyword arguments passed in the consturctor are used as the default
    Loader arguments passed to on each expander call. This arguments can be
    overriden with specific noader arguments passed on each expander call.

    Example::

        >>> def filter_world(x):
        ...     return None if x == 'world' else x
        ...
        >>> from scrapy.newitem.loader.expanders import TreeExpander
        >>> expander = TreeExpander(filter_world, str.upper)
        >>> expander(['hello', 'world', 'this', 'is', 'scrapy'])
        ['HELLO, 'THIS', 'IS', 'SCRAPY']


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

        >>> from scrapy.newitem.loader.reducers import TakeFirst
        >>> reducer = TakeFirst()
        >>> reducer(['', 'one', 'two', 'three'])
        'one'

.. class:: Identity

    Return the values to reduce unchanged, so it's used for multi-valued
    fields. It doesn't receive any constructor arguments.

    Example::

        >>> from scrapy.newitem.loader.reducers import Identity
        >>> reducer = Identity()
        >>> reducer(['one', 'two', 'three'])
        ['one', 'two', 'three']

.. class:: Join(separator=u' ')

    Return a the values to reduce joined with the separator given in the
    constructor, which defaults to ``u' '``.

    When using the default separator, this reducer is equivalent to the
    function: ``u' '.join``

    Examples::

        >>> from scrapy.newitem.loader.reducers import Join
        >>> reducer = Join()
        >>> reducer(['one', 'two', 'three'])
        u'one two three'
        >>> reducer = Join('<br>')
        >>> reducer(['one', 'two', 'three'])
        u'one<br>two<br>three'
