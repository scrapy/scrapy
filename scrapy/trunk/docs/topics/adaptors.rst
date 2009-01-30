.. _topics-adaptors:

========
Adaptors
========

.. warning::
   
   Adaptors are an experimental feature of Scrapy, which mean its API is not
   yet stable and could suffer minor changes before the next stable release.

Quick overview
==============

Scrapy's adaptors are a nice feature attached to :class:`RobustScrapedItem`
that allow you to easily modify (adapt to your needs) any kind of information
you want to put in your items at assignation time.

The following diagram shows the data flow from the moment you call the
``attribute`` method until the attribute is actually set.

.. image:: _images/adaptors_diagram.png

As you can see, adaptor pipelines are executed in tree form; which means that,
for each of the values you pass to the ``attribute`` method, the first adaptor
will be applied. Then, for each of the resulting values of the first adaptor,
the second adaptor will be called, and so on.  This process will end up with a
list of adapted values, which may contain zero, one, or many values.

In case the attribute is a single-valued (this is defined in the item's
``ATTRIBUTES`` dictionary), the first element of this list will be set, unless
you call the ``attribute`` method with the add parameter as True, in which case
the item's method ``_add_single_attributes`` will be called with the
attribute's name, type, and the list of attributes to join as parameters.  By
default, this method raises NotImplementedError, so you should override it in
your items in order to join any kind of objects.

If the attribute is a multivalued, the resulting list will be set to the item
as is, unless you use -again- add=True, in which case the list of
already-existing values (if any) will be extended with the new one.pgq

Adaptor Pipelines
=================

.. class:: AdaptorPipe(adaptors=None)

    An instance of this class represents an adaptor pipeline to be set for
    adapting a certain item's attribute.  It provides some useful methods for
    adding/removing adaptors, and takes care of executing them properly.
    Usually this class is not used directly, since the items already provide
    ways to manage adaptors without having to handle AdaptorPipes.

    :param adaptors: A list of callables to be added as adaptors at
        instancing time.

    Methods:

    .. method:: add_adaptor(adaptor, position=None)

        This method is used for adding adaptors to the pipeline given
        a certain position.

        :param adaptor: Any callable that works as an adaptor
        :param position: An integer meaning the position in which the adaptor
            will be inserted. If it's None the adaptor will be appended at
            the end of the pipeline.

Usage
=====

As it was previously said, in order to use adaptor pipelines you must inherit
your items from the :class:`RobustScrapedItem` class.  If you don't know
anything about these items, read the :ref:`topics-items` reference first.

Once you've created your own item class (inherited from
:class:`RobustScrapedItem`) with the attributes you're going to use, you have
to add adaptor pipelines to each attribute you'd like to adapt data for.  For
doing so, RobustScrapedItems provide some useful methods like ``set_adaptors``,
``set_attrib_adaptors``, and more (which are also described in its reference)
so that you don't need to work with :class:`AdaptorPipe` objects directly.

Adaptors
--------

Let's now talk a bit about adaptors (singularly), what are them, and how
should they be implemented?

Adaptors are basically, any callable that receives
a value, modifies it, and returns a new value (or more) so that the next
adaptor goes on with another adapting task (or not).  This is done this way to
make the process of modifying information very customizable, and also to make
adaptors reusable, since they are intended to be small functions designed for
simple purposes that can be applied in many different cases.  For example, you
could make an adaptor for removing any <b> tags in a text, like this::

    >>> B_TAG_RE = re.compile(r'</?b\s*>')
    >>> def remove_b_tags(text):
    >>>     return B_TAG_RE.sub('', text)

Then you could easily add this adaptor to a certain attribute's pipeline like
this::

    >>> item = MyItem()
    >>> item.add_adaptor('text', remove_b_tags)
    >>> item.attribute('text', u'<b>some random text in bold</b> and some random text in normal font')
    >>> item.text
        u'some random text in bold and some random text in normal font'

As you can see, this would make any value that you set to the item through the
``attribute`` method first pass through the ``remove_b_tags`` adaptor, which
would also replace any matching tag with an empty string.

----

But anyway, let's now think of a bit more complicated (and useless) example:
let's say you want to scrape a text, split it into single letters, strip the
vowels, turn the rest to capital letters, and join them again.  In this case,
we could use three simple adaptors to process our data, plus a customized
:class:`RobustScrapedItem` for joining single text attributes; let's see an
example::

    >>> # First of all, we define the item class we're going to use
    >>> from string import ascii_letters
    >>> from scrapy.contrib.item import RobustScrapedItem
    >>> class MyItem(RobustScrapedItem):
    >>>    ATTRIBUTES = {
    >>>        'text': basestring,
    >>>    }

    >>>    def _add_single_attributes(self, attrname, attrtype, attributes):
    >>>        return ''.join(attributes)

    >>> # Now we'll write the needed adaptors
    >>> def to_letters(text):
    >>>     return tuple(letter for letter in text)

    >>> def is_vowel(letter):
    >>>     if letter in ascii_letters and letter.lower() not in ('a', 'e', 'i', 'o', 'u'):
    >>>        return letter

    >>> def to_upper(letter):
    >>>     return letter.upper()

    >>> # Finally, we'll join all the pieces and see how it works
    >>> item = MyItem()
    >>> item.set_attrib_adaptors('text', [
    >>>     to_letters,
    >>>     is_vowel,
    >>>     to_upper,
    >>> ])

Let's now try with an example text to see what happens::

    >>> item.attribute('text', 'pi', 'wind', add=True)
    >>> item.text
    'PWND'

More complex adaptors
---------------------

Now, after using adaptors a bit, you may find yourself in situations where you need
to use adaptors that receive other parameters from the ``attribute`` method
apart from the value to adapt.

For example, imagine you have an adaptor that removes certain characters from strings
you provide. Would you make an adaptor for each combination of characters you'd like
to strip? Of course not!

The way to handle this cases, is to make an adaptor that apart from receiving a value,
as any other adaptor, receives a parameter called ``adaptor_args``.
It's important that the parameter is called this way, since Scrapy finds out whether
an adaptor is able to receive extra parameters or not by making instrospection
and looking for a parameter called this way in the adaptor's parameters list.

The information this parameter will receive won't be anything else but the same dictionary
of keyword arguments that you pass to the ``attribute`` method when calling it.

But let's get back to the characters example, how would we implement this?
Quite simmilar to any other adaptor, let's see::

    def strip_chars(value, adaptor_args):
        chars = adaptor_args.get('strip_chars', [])
        for char in chars:
            value = value.replace(char, '')
        return value

Then, after creating an item and adding the adaptor to one of its pipelines, we could do::

    >>> item.attribute('text', 'Hi, my name is John', strip_chars=['a', 'i', 'm'])
    >>> item.text
    'H, y ne s John'

Debugging
=========

While you're coding spiders and adaptors, you usually need to know exactly what
does Scrapy do under the hood with the values you provide.  There's a setting
called :setting:``ADAPTORS_DEBUG`` for this purpose that makes Scrapy print
debugging messages each time an adaptors pipeline is run, specifying which
attribute is being adapted data for, the input/output values of each adaptor in
the pipeline, and the input/output of ``_add_single_attributes`` (in some
cases).

You can enable this setting as any other, either by adding it to your settings
file, or by enabling the environment variable ``SCRAPY_ADAPTORS_DEBUG``.
