.. _topics-leaks:

======================
Debugging memory leaks
======================

In Scrapy, objects such as Requests, Responses and Items have a finite
lifetime: they are created, used for a while, and finally destroyed.

From all those objects, the Request is probably the one with the longest
lifetime, as it stays waiting in the Scheduler queue until it's time to process
it. For more info see :ref:`topics-architecture`.

As these Scrapy objects have a (rather long) lifetime, there is always the risk
of accumulating them in memory without releasing them properly and thus causing
what is known as a "memory leak".

To help debugging memory leaks, Scrapy provides a built-in mechanism for
tracking objects references called :ref:`trackref <topics-leaks-trackrefs>`,
and you can also use a third-party library called :ref:`Guppy
<topics-leaks-guppy>` for more advanced memory debugging (see below for more
info). Both mechanisms must be used from the :ref:`Telnet Console
<topics-telnetconsole>`.

Common causes of memory leaks
=============================

It happens quite often (sometimes by accident, sometimes on purpose) that the
Scrapy developer passes objects referenced in Requests (for example, using the
:attr:`~scrapy.http.Request.meta` attribute or the request callback function)
and that effectively bounds the lifetime of those referenced objects to the
lifetime of the Request. This is, by far, the most common cause of memory leaks
in Scrapy projects, and a quite difficult one to debug for newcomers.

In big projects, the spiders are typically written by different people and some
of those spiders could be "leaking" and thus affecting the rest of the other
(well-written) spiders when they get to run concurrently, which, in turn,
affects the whole crawling process. 

At the same time, it's hard to avoid the reasons that cause these leaks
without restricting the power of the framework, so we have decided not to
restrict the functionally but provide useful tools for debugging these leaks,
which quite often consist in an answer to the question: *which spider is leaking?*.

The leak could also come from a custom middleware, pipeline or extension that
you have written, if you are not releasing the (previously allocated) resources
properly. For example, if you're allocating resources on
:signal:`spider_opened` but not releasing them on :signal:`spider_closed`.

.. _topics-leaks-trackrefs:

Debugging memory leaks with ``trackref``
========================================

``trackref`` is a module provided by Scrapy to debug the most common cases of
memory leaks. It basically tracks the references to all live Requests,
Responses, Item and Selector objects. 

You can enter the telnet console and inspect how many objects (of the classes
mentioned above) are currently alive using the ``prefs()`` function which is an
alias to the :func:`~scrapy.utils.trackref.print_live_refs` function::

    telnet localhost 6023

    >>> prefs()
    Live References

    ExampleSpider                       1   oldest: 15s ago
    HtmlResponse                       10   oldest: 1s ago
    Selector                            2   oldest: 0s ago
    FormRequest                       878   oldest: 7s ago

As you can see, that report also shows the "age" of the oldest object in each
class. 

If you do have leaks, chances are you can figure out which spider is leaking by
looking at the oldest request or response. You can get the oldest object of
each class using the :func:`~scrapy.utils.trackref.get_oldest` function like
this (from the telnet console).

Which objects are tracked?
--------------------------

The objects tracked by ``trackrefs`` are all from these classes (and all its
subclasses):

* ``scrapy.http.Request``
* ``scrapy.http.Response``
* ``scrapy.item.Item``
* ``scrapy.selector.Selector``
* ``scrapy.spider.Spider``

A real example
--------------

Let's see a concrete example of an hypothetical case of memory leaks.

Suppose we have some spider with a line similar to this one::

    return Request("http://www.somenastyspider.com/product.php?pid=%d" % product_id,
        callback=self.parse, meta={referer: response}")

That line is passing a response reference inside a request which effectively
ties the response lifetime to the requests' one, and that would definitely
cause memory leaks.

Let's see how we can discover which one is the nasty spider (without knowing it
a-priori, of course) by using the ``trackref`` tool.

After the crawler is running for a few minutes and we notice its memory usage
has grown a lot, we can enter its telnet console and check the live
references::

    >>> prefs()
    Live References

    SomenastySpider                     1   oldest: 15s ago
    HtmlResponse                     3890   oldest: 265s ago
    Selector                            2   oldest: 0s ago
    Request                          3878   oldest: 250s ago

The fact that there are so many live responses (and that they're so old) is
definitely suspicious, as responses should have a relatively short lifetime
compared to Requests. So let's check the oldest response::

    >>> from scrapy.utils.trackref import get_oldest
    >>> r = get_oldest('HtmlResponse')
    >>> r.url
    'http://www.somenastyspider.com/product.php?pid=123'

There it is. By looking at the URL of the oldest response we can see it belongs
to the ``somenastyspider.com`` spider. We can now go and check the code of that
spider to discover the nasty line that is generating the leaks (passing
response references inside requests).

If you want to iterate over all objects, instead of getting the oldest one, you
can use the :func:`iter_all` function::

    >>> from scrapy.utils.trackref import iter_all
    >>> [r.url for r in iter_all('HtmlResponse')]
    ['http://www.somenastyspider.com/product.php?pid=123',
     'http://www.somenastyspider.com/product.php?pid=584',
    ...

Too many spiders?
-----------------

If your project has too many spiders, the output of ``prefs()`` can be
difficult to read. For this reason, that function has a ``ignore`` argument
which can be used to ignore a particular class (and all its subclases). For
example, using::

    >>> from scrapy.spider import Spider
    >>> prefs(ignore=Spider)

Won't show any live references to spiders.

.. module:: scrapy.utils.trackref
   :synopsis: Track references of live objects

scrapy.utils.trackref module
----------------------------

Here are the functions available in the :mod:`~scrapy.utils.trackref` module.

.. class:: object_ref

    Inherit from this class (instead of object) if you want to track live
    instances with the ``trackref`` module.

.. function:: print_live_refs(class_name, ignore=NoneType)

    Print a report of live references, grouped by class name.

    :param ignore: if given, all objects from the specified class (or tuple of
        classes) will be ignored.
    :type ignore: class or classes tuple

.. function:: get_oldest(class_name)

    Return the oldest object alive with the given class name, or ``None`` if
    none is found. Use :func:`print_live_refs` first to get a list of all
    tracked live objects per class name.

.. function:: iter_all(class_name)

    Return an iterator over all objects alive with the given class name, or
    ``None`` if none is found. Use :func:`print_live_refs` first to get a list
    of all tracked live objects per class name.

.. _topics-leaks-guppy:

Debugging memory leaks with Guppy
=================================

``trackref`` provides a very convenient mechanism for tracking down memory
leaks, but it only keeps track of the objects that are more likely to cause
memory leaks (Requests, Responses, Items, and Selectors). However, there are
other cases where the memory leaks could come from other (more or less obscure)
objects. If this is your case, and you can't find your leaks using ``trackref``,
you still have another resource: the `Guppy library`_. 

.. _Guppy library: http://pypi.python.org/pypi/guppy

If you use ``setuptools``, you can install Guppy with the following command::

    easy_install guppy

.. _setuptools: http://pypi.python.org/pypi/setuptools

The telnet console also comes with a built-in shortcut (``hpy``) for accessing
Guppy heap objects. Here's an example to view all Python objects available in
the heap using Guppy::

    >>> x = hpy.heap()
    >>> x.bytype
    Partition of a set of 297033 objects. Total size = 52587824 bytes.
     Index  Count   %     Size   % Cumulative  % Type
         0  22307   8 16423880  31  16423880  31 dict
         1 122285  41 12441544  24  28865424  55 str
         2  68346  23  5966696  11  34832120  66 tuple
         3    227   0  5836528  11  40668648  77 unicode
         4   2461   1  2222272   4  42890920  82 type
         5  16870   6  2024400   4  44915320  85 function
         6  13949   5  1673880   3  46589200  89 types.CodeType
         7  13422   5  1653104   3  48242304  92 list
         8   3735   1  1173680   2  49415984  94 _sre.SRE_Pattern
         9   1209   0   456936   1  49872920  95 scrapy.http.headers.Headers
    <1676 more rows. Type e.g. '_.more' to view.>

You can see that most space is used by dicts. Then, if you want to see from
which attribute those dicts are referenced, you could do::

    >>> x.bytype[0].byvia
    Partition of a set of 22307 objects. Total size = 16423880 bytes.
     Index  Count   %     Size   % Cumulative  % Referred Via:
         0  10982  49  9416336  57   9416336  57 '.__dict__'
         1   1820   8  2681504  16  12097840  74 '.__dict__', '.func_globals'
         2   3097  14  1122904   7  13220744  80
         3    990   4   277200   2  13497944  82 "['cookies']"
         4    987   4   276360   2  13774304  84 "['cache']"
         5    985   4   275800   2  14050104  86 "['meta']"
         6    897   4   251160   2  14301264  87 '[2]'
         7      1   0   196888   1  14498152  88 "['moduleDict']", "['modules']"
         8    672   3   188160   1  14686312  89 "['cb_kwargs']"
         9     27   0   155016   1  14841328  90 '[1]'
    <333 more rows. Type e.g. '_.more' to view.>

As you can see, the Guppy module is very powerful but also requires some deep
knowledge about Python internals. For more info about Guppy, refer to the
`Guppy documentation`_.

.. _Guppy documentation: http://guppy-pe.sourceforge.net/

.. _topics-leaks-without-leaks:

Leaks without leaks
===================

Sometimes, you may notice that the memory usage of your Scrapy process will
only increase, but never decrease. Unfortunately, this could happen even
though neither Scrapy nor your project are leaking memory. This is due to a
(not so well) known problem of Python, which may not return released memory to
the operating system in some cases. For more information on this issue see:

* `Python Memory Management <http://evanjones.ca/python-memory.html>`_
* `Python Memory Management Part 2 <http://evanjones.ca/python-memory-part2.html>`_
* `Python Memory Management Part 3 <http://evanjones.ca/python-memory-part3.html>`_

The improvements proposed by Evan Jones, which are detailed in `this paper`_,
got merged in Python 2.5, but this only reduces the problem, it doesn't fix it
completely. To quote the paper:

    *Unfortunately, this patch can only free an arena if there are no more
    objects allocated in it anymore. This means that fragmentation is a large
    issue. An application could have many megabytes of free memory, scattered
    throughout all the arenas, but it will be unable to free any of it. This is
    a problem experienced by all memory allocators. The only way to solve it is
    to move to a compacting garbage collector, which is able to move objects in
    memory. This would require significant changes to the Python interpreter.*

This problem will be fixed in future Scrapy releases, where we plan to adopt a
new process model and run spiders in a pool of recyclable sub-processes.

.. _this paper: http://evanjones.ca/memoryallocator/
