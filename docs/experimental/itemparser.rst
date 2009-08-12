.. _topics-itemparser:

============
Item Parsers
============

.. module:: scrapy.contrib.itemparser
   :synopsis: Item Parser class

Item Parser provide a convenient mechanism for populating scraped :ref:`Items
<topics-newitems>`. Even though Items can be populated using their own
dictionary-like API, the Item Parsers provide a much more convenient API for
populating them from a scraping process, by automating some common tasks like
parsing the raw extracted data before assigning it.

In other words, :ref:`Items <topics-newitems>` provide the *container* of
scraped data, while Item Parsers provide the mechanism for *populating* that
container.

Item Parsers are designed to provide a flexible, efficient and easy mechanism
for extending and overriding different field parsing rules, either by spider,
or by source format (HTML, XML, etc) without becoming a nightmare to maintain.

Using Item Parsers to populate items
====================================

To use an Item Parser, you must first instantiate it. You can either
instantiate it with an Item object or without one, in which case an Item is
automatically instantiated in the Item Parser constructor using the Item class
specified in the :attr:`ItemParser.default_item_class` attribute.

Then, you start collecting values into the Item Parser, typically using using
:ref:`XPath Selectors <topics-selectors>`. You can add more than one value to
the same item field, the Item Parser will know how to "join" those values later
using a proper parser function.

Here is a typical Item Parser usage in a :ref:`Spider <topics-spiders>`, using
the :ref:`Product item <topics-newitems-declaring>` declared in the :ref:`Items
chapter <topics-newitems>`::

    from scrapy.contrib.itemparser import XPathItemParser
    from scrapy.xpath import HtmlXPathSelector
    from myproject.items import Product

    def parse(self, response):
        p = XPathItemParser(item=Product(), response=response)
        p.add_xpath('name', '//div[@class="product_name"]')
        p.add_xpath('name', '//div[@class="product_title"]')
        p.add_xpath('price', '//p[@id="price"]')
        p.add_xpath('stock', '//p[@id="stock"]')
        p.add_value('last_updated', 'today') # you can also use literal values
        return p.populate_item()

By quickly looking at that code we can see the ``name`` field is being
extracted from two different XPath locations in the page:

1. ``//div[@class="product_name"]``
2. ``//div[@class="product_title"]``

In other words, data is being collected by extracting it from two XPath
locations, using the :meth:`~XPathItemParser.add_xpath` method. This is the data
that will be assigned to the ``name`` field later.

Afterwards, similar calls are used for ``price`` and ``stock`` fields, and
finally the ``last_update`` field is populated directly with a literal value
(``today``) using a different method: :meth:`~ItemParser.add_value`.

Finally, when all data is collected, the :meth:`ItemParser.populate_item`
method is called which actually populates and returns the item populated with
the data previously extracted and collected with the
:meth:`~XPathItemParser.add_xpath` and :meth:`~ItemParser.add_value` calls.

.. _topics-itemparser-parsers:

Input and Output parsers
========================

An Item Parser contains one input parser and one output parser for each (item)
field. The input parser processes the extracted data as soon as it's received
(through the :meth:`~XPathItemParser.add_xpath` or
:meth:`~ItemParser.add_value` methods) and the result of the input parser is
collected and kept inside the ItemParser. After collecting all data, the
:meth:`ItemParser.populate_item` method is called to populate and get the
populated :class:`~scrapy.newitem.Item` object.  That's when the output parser
is called with the data previously collected (and processed using the input
parser). The result of the output parser is the final value that gets assigned
to the item.

Let's see an example to illustrate how this input and output parsers are
called for a particular field (the same applies for any other field)::

    p = XPathItemParser(Product(), some_xpath_selector)
    p.add_xpath('name', xpath1) # (1)
    p.add_xpath('name', xpath2) # (2)
    return p.populate_item() # (3)

So what happens is:

1. Data from ``xpath1`` is extracted, and passed through the *input parser* of
   the ``name`` field. The result of the input parser is collected and kept in
   the Item Parser (but not yet assigned to the item).

2. Data from ``xpath2`` is extracted, and passed through the same *input
   parser* used in (1). The result of the input parser is appended to the data
   collected in (1) (if any).

3. The data collected in (1) and (2) is passed through the *output parser* of
   the ``name`` field. The result of the output parser is the value assigned to
   the ``name`` field in the item.

It's worth noticing that parsers are just callable objects, which are called
with the data to be parsed, and return a parsed value. So you can use any
function as input or output parser, provided they can receive only one
positional (required) argument.

The other thing you need to keep in mind is that the values returned by input
parsers are collected internally (in lists) and then passed to output parsers
to populate the fields, so output parsers should expect iterables as input. 

Last, but not least, Scrapy comes with some :ref:`commonly used parsers
<topics-itemparser-available-parsers>` built-in for convenience.


Declaring Item Parsers
======================

Item Parsers are declared like Items, by using a class definition syntax. Here
is an example::

    from scrapy.contrib.itemparser import ItemParser
    from scrapy.contrib.itemparser.parsers import TakeFirst, ApplyConcat, Join

    class ProductParser(ItemParser):

        default_expander = TakeFirst()

        name_in = ApplyConcat(unicode.title)
        name_out = Join()

        price_in = ApplyConcat(unicode.strip)
        price_out = TakeFirst()

        # ...

As you can see, input parsers are declared using the ``_in`` suffix while
output parsers are declared using the ``_out`` suffix. And you can also declare
a default input/output parsers using the
:attr:`ItemParser.default_input_parser` and
:attr:`ItemParser.default_output_parser` attributes.

.. _topics-itemparser-parsers-declaring:

Declaring Input and Output Parsers
==================================

As seen in the previous section, input and output parsers can be declared in
the Item Parser definition, and it's very common to declare input parsers this
way. However, there is one more place where you can specify the input and
output parsers to use: in the :ref:`Item Field <topics-newitems-fields>`
metadata. Here is an example::

    from scrapy.newitem import Item, Field
    from scrapy.contrib.itemparser.parser import ApplyConcat, Join, TakeFirst

    from scrapy.utils.markup import remove_entities
    from myproject.utils import filter_prices

    class Product(Item):
        name = Field(
            input_parser=ApplyConcat(remove_entities),
            output_parser=Join(),
        )
        price = Field(
            default=0,
            input_parser=ApplyConcat(remove_entities, filter_prices),
            output_parser=TakeFirst(),
        )

The precedence order, for both input and output parsers, is as follows:

1. Item Parser field-specific attributes: ``field_in`` and ``field_out`` (most
   precedence)
2. Field metadata (``input_parser`` and ``output_parser`` key)
3. Item Parser defaults: :meth:`ItemParser.default_expander` and
   :meth:`ItemParser.default_output_parser` (least precedence)

See also: :ref:`topics-itemparser-extending`.

.. _topics-itemparser-context:

Item Parser Context
===================

The Item Parser Context is a dict of arbitrary key/values which is shared among
all input and output parsers in the Item Parser. It can be passed when
declaring, instantiating or using Item Parser. They are used to modify the
behaviour of the input/output parsers.

For example, suppose you have a function ``parse_length`` which receives a text
value and extracts a length from it::

    def parse_length(text, parser_context):
        unit = parser_context.get('unit', 'm')
        # ... length parsing code goes here ...
        return parsed_length

By accepting a ``parser_context`` argument the function is explicitly telling
the Item Parser that is able to receive an Item Parser context, so the Item
Parser passes the currently active context when calling it, and the parser
function (``parse_length`` in this case) can thus use them.

There are several ways to modify Item Parser context values:

1. By modifying the currently active Item Parser context
(:meth:`ItemParser.context` attribute)::

    parser = ItemParser(product, unit='cm')
    parser.context['unit'] = 'cm'

2. On Item Parser instantiation (the keyword arguments of Item Parser
   constructor are stored in the Item Parser context)::

    p = ItemParser(product, unit='cm')

2. On Item Parser declaration, for those input/output parsers that support
   instatiating them with a Item Parser context. :class:`ApplyConcat` is one of
   them::

    class ProductParser(ItemParser):
        length_out = ApplyConcat(parse_length, unit='cm')


ItemParser objects
==================

.. class:: ItemParser([item], \**kwargs)

    Return a new Item Parser for populating the given Item. If no item is
    given, one is instantiated automatically using the class in
    :attr:`default_item_class`.

    The item and the remaining keyword arguments are assigned to the Parser
    context (accesible through the :attr:`context` attribute).

    .. method:: add_value(field_name, value)

        Add the given ``value`` for the given field.

        The value is passed through the :ref:`field input parser
        <topics-itemparser-parsers>` and its result appened to the data
        collected for that field. If the field already contains collected data,
        the new data is added.

        Examples::

            parser.add_value('name', u'Color TV')
            parser.add_value('colours', [u'white', u'blue'])
            parser.add_value('length', u'100', default_unit='cm')

    .. method:: replace_value(field_name, value)

        Similar to :meth:`add_value` but replaces the collected data with the
        new value instead of adding it.

    .. method:: populate_item()

        Populate the item with the data collected so far, and return it. The
        data collected is first passed through the :ref:`field output parsers
        <topics-itemparser-parsers>` to get the final value to assign to each
        item field.

    .. method:: get_collected_values(field_name)

        Return the collected values for the given field.

    .. method:: get_output_value(field_name)

        Return the collected values parsed using the output parser, for the
        given field. This method doesn't populate or modify the item at all.

    .. method:: get_input_parser(field_name)

        Return the input parser for the given field.

    .. method:: get_output_parser(field_name)

        Return the output parser for the given field.

    .. attribute:: item

        The :class:`~scrapy.newitem.Item` object being parsed by this Item
        Parser.

    .. attribute:: context

        The currently active :ref:`Context <topics-itemparser-context>` of this
        Item Parser.

    .. attribute:: default_item_class

        An Item class (or factory), used to instantiate items when not given in
        the constructor.

    .. attribute:: default_input_parser

        The default input parser to use for those fields which don't specify
        one.

    .. attribute:: default_output_parser

        The default output parser to use for those fields which don't specify
        one.

.. class:: XPathItemParser([item, selector, response], \**kwargs)

    The :class:`XPathItemParser` class extends the :class:`ItemParser` class
    providing more convenient mechanisms for extracting data from web pages
    using :ref:`XPath selectors <topics-selectors>`.

    :class:`XPathItemParser` objects accept two more additional parameters in
    their constructors:

    :param selector: The selector to extract data from, when using the
        :meth:`add_xpath` or :meth:`replace_xpath` method.
    :type selector: :class:`~scrapy.xpath.XPathSelector` object

    :param response: The response used to construct the selector using the
        :attr:`default_selector_class`, unless the selector argument is given,
        in which case this argument is ignored.
    :type response: :class:`~scrapy.http.Response` object

    .. method:: add_xpath(field_name, xpath, re=None)

        Similar to :meth:`ItemParser.add_value` but receives an XPath instead of a
        value, which is used to extract a list of unicode strings from the
        selector associated with this :class:`XPathItemParser`. If the ``re``
        argument is given, it's used for extrating data from the selector using
        the :meth:`~scrapy.xpath.XPathSelector.re` method.

        :param xpath: the XPath to extract data from
        :type xpath: str

        :param re: a regular expression to use for extracting data from the
            selected XPath region
        :type re: str or compiled regex

        Examples::

            # HTML snippet: <p class="product-name">Color TV</p>
            parser.add_xpath('name', '//p[@class="product-name"]')
            # HTML snippet: <p id="price">the price is $1200</p>
            parser.add_xpath('price', '//p[@id="price"]', re='the price is (.*)')

    .. method:: replace_xpath(field_name, xpath, re=None)

        Similar to :meth:`add_xpath` but replaces collected data instead of
        adding it.

    .. attribute:: default_selector_class

        The class used to construct the :attr:`selector` of this
        :class:`XPathItemParser`, if only a response is given in the constructor.
        If a selector is given in the constructor this attribute is ignored.
        This attribute is sometimes overridden in subclasses.

    .. attribute:: selector

        The :class:`~scrapy.xpath.XPathSelector` object to extract data from.
        It's either the selector given in the constructor or one created from
        the response given in the constructor using the
        :attr:`default_selector_class`. This attribute is meant to be
        read-only.

.. _topics-itemparser-extending:

Reusing and extending Item Parsers
==================================

As your project grows bigger and acquires more and more spiders, maintenance
becomes a fundamental problem, specially when you have to deal with many
different parsing rules for each spider, having a lot of exceptions, but also
wanting to reuse the common parsers.

Item Parsers are designed to ease the maintenance burden of parsing rules,
without loosing flexibility and, at the same time, providing a convenient
mechanism for extending and overriding them. For this reason Item Parsers
support traditional Python class inheritance for dealing with differences of
specific spiders (or group of spiders).

Suppose, for example, that some particular site encloses their product names in
three dashes (ie. ``---Plasma TV---``) and you don't want to end up scraping
those dashes in the final product names.

Here's how you can remove those dashes by reusing and extending the default
Product Item Parser (``ProductParser``)::

    from scrapy.contrib.itemparser.parsers import ApplyConcat
    from myproject.itemparsers import ProductParser

    def strip_dashes(x):
        return x.strip('-')

    class SiteSpecificParser(ProductParser):
        name_in = ApplyConcat(ProductParser.name_in, strip_dashes)

Another case where extending Item Parsers can be very helpful is when you have
multiple source formats, for example XML and HTML. In the XML version you may
want to remove ``CDATA`` occurrences. Here's an example of how to do it::

    from scrapy.contrib.itemparser.parsers import ApplyConcat
    from myproject.itemparsers import ProductParser
    from myproject.utils.xml import remove_cdata

    class XmlProductParser(ProductParser):
        name_in = ApplyConcat(remove_cdata, ProductParser.name_in)

And that's how you typically extend input parsers.

As for output parsers, it is more common to declare them in the field metadata,
as they usually depend only on the field and not on each specific site parsing
rule (as input parsers do). See also:
:ref:`topics-itemparser-parsers-declaring`.

There are many other possible ways to extend, inherit and override your Item
Parsers, and different Item Parsers hierarchies may fit better for different
projects. Scrapy only provides the mechanism, it doesn't impose any specific
organization of your Parsers collection - that's up to you and your project
needs.

.. _topics-itemparser-available-parsers:

Available built-in parsers
==========================

Even though you can use any callable function as input and output parsers,
Scrapy provides some commonly used parsers, which are described below. Some of
them, like the :class:`ApplyConcat` (which is typically used as input parser)
composes the output of several functions executed in order, to produce the
final parsed value.

Here is a list of all built-in parsers:

.. _topics-itemparser-Applyconcat:

ApplyConcat parser
------------------

The ApplyConcat parser is the recommended parser to use if you want to
concatenate the processing of several functions in a pipeline.

.. module:: scrapy.contrib.itemparser.parsers
   :synopsis: Parser functions to use with Item Parsers

.. class:: ApplyConcat(\*functions, \**default_parser_context)

    A parser which applies the given functions consecutively, in order,
    concatenating their results before next function call. So each function
    returns a list of values (though it could return ``None`` or a signle value
    too) and the next function is called once for each of those values,
    receiving one of those values as input each time. The output of each
    function call (for each input value) is concatenated and each values of the
    concatenation is used to call the next function, and the process repeats
    until there are no functions left.
    
    Each function can optionally receive a ``parser_context`` parameter, which
    will contain the currently active :ref:`Item Parser context
    <topics-itemparser-context>`. 

    The keyword arguments passed in the consturctor are used as the default
    Item Parser context values passed on each function call. However, the final
    Item Parser context values passed to funtions get overriden with the
    currently active Item Parser context accesible through the
    :meth:`ItemParser.context` attribute.

    Example::

        >>> def filter_world(x):
        ...     return None if x == 'world' else x
        ...
        >>> from scrapy.contrib.itemparser.parsers import ApplyConcat
        >>> parser = ApplyConcat(filter_world, str.upper)
        >>> parser(['hello', 'world', 'this', 'is', 'scrapy'])
        ['HELLO, 'THIS', 'IS', 'SCRAPY']

.. class:: TakeFirst

    Return the first non null/empty value from the values to received, so it's
    typically used as output parser of single-valued fields. It doesn't receive
    any constructor arguments, nor accepts a Item Parser context.

    Example::

        >>> from scrapy.contrib.itemparser.parsers import TakeFirst
        >>> parser = TakeFirst()
        >>> parser(['', 'one', 'two', 'three'])
        'one'

.. class:: Identity

    Return the original values unchanged. It doesn't receive any constructor
    arguments nor accepts a Item Parser context.

    Example::

        >>> from scrapy.contrib.itemparser.parsers import Identity
        >>> parser = Identity()
        >>> parser(['one', 'two', 'three'])
        ['one', 'two', 'three']

.. class:: Join(separator=u' ')

    Return the values joined with the separator given in the constructor, which
    defaults to ``u' '``. It doesn't accept a Item Parser context.

    When using the default separator, this parser is equivalent to the
    function: ``u' '.join``

    Examples::

        >>> from scrapy.contrib.itemparser.parsers import Join
        >>> parser = Join()
        >>> parser(['one', 'two', 'three'])
        u'one two three'
        >>> parser = Join('<br>')
        >>> parser(['one', 'two', 'three'])
        u'one<br>two<br>three'
