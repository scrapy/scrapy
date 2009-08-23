.. _topics-leaks:

======================
Debugging memory leaks
======================

In Scrapy, objects such as Requests, Responses and Items have a finite
lifetime: they are created, used for a while, and finally destroyed.

From all those objects the Request is probably the one with the longest
lifetime, as it stays waiting in the Scheduler queue until it's time to process
it. For more info see :ref:`topics-architecture`.

As these Scrapy objects have a (rather long) lifetime there is always the risk
accumulated them in memory without releasing them properly and thus causing
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
(well-written) spiders when they get to run concurrently which, in turn,
affects the whole crawling process. 

At the same time, it's hard to avoid the reasons that causes these leaks
without restricting the power of the framework, so we have decided not to
restrict the functionally but provide useful tools for debugging these leaks,
which quite often consists in answer the question: *which spider is leaking?*.

The leak could also come from a custom middleware, pipeline or extension that
you have written, if you are not releasing the (previously allocated) resources
properly. For example, if you're allocating resources on
:signal:`domain_opened` but not releasing them on :signal:`domain_closed`.

.. _topics-leaks-trackrefs:

Debugging memory leaks with ``trackref``
========================================

``trackref`` is a module provided by Scrapy to debug the most common cases of
memory leaks. It basically tracks the references to all live Requests,
Responses, Item and Selector objects. 

To active the ``trackref`` module, enable the :setting:`TRACK_REFS` setting. It
only imposes a minor performance impact so it should be OK for use it in
production environments.

Once you have ``trackref`` enabled you can enter the telnet console and inspect
how many objects (of the classes mentioned above) are currently alive using the
``prefs()`` function which is an alias to the
:func:`~scrapy.utils.trackref.print_live_refs` function::

    telnet localhost 6023

    >>> prefs()
    Live References

    HtmlResponse                       10   oldest: 1s ago
    XPathSelector                       2   oldest: 0s ago
    FormRequest                       878   oldest: 7s ago

As you can see, that report also shows the "age" of the oldest object in each
class. 

If you do have leaks, chances are you can figure out which spider is leaking by
looking at the oldest request or response. You can get the oldest object of
each class using the :func:`~scrapy.utils.trackref.get_oldest` function like
this (from the telnet console).

A real example
--------------

Let's see a concrete example of an hypothetical case of memory leaks.

Suppose we have some spider with a line similar to this one::

    return Request("http://www.somenastyspider.com/product.php?pid=%d" % product_id,
        callback=self.parse, meta={referer: response}")

That line is passing a response reference inside a request which effectively
ties the response lifetime to the requests one, and that's would definitely
cause memory leaks.

Let's see how we can discover which one is the nasty spider (without knowing it
a-priori, of course) by using the ``trackref`` tool.

After the crawler is running for a few minutes and we notice its memory usage
has grown a lot, we can enter its telnet console and check the live
references::

    >>> prefs()
    Live References

    HtmlResponse                     3890   oldest: 265s ago
    XPathSelector                       2   oldest: 0s ago
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

.. module:: scrapy.utils.trackref
   :synopsis: Track references of live objects

scrapy.utils.trackref module
----------------------------

Here are the functions available in the :mod:`~scrapy.utils.trackref` module.

.. class:: object_ref

    Inherit from this class (instead of object) if you want to track live
    instances with the ``trackref`` module.

.. function:: print_live_refs(class_name)

    Print a report of live references, grouped by class name.

.. function:: get_oldest(class_name)

    Return the oldest object alive with the given class name, or ``None`` if
    none is found. Use :func:`print_live_refs` first to get a list of all
    tracked live objects.

.. _topics-leaks-guppy:

Debugging memory leaks with Guppy
=================================

``trackref`` provides a very convenient mechanism for tracking down memory
leaks, but it only keeps track of the objects that are more likely to cause
memory leaks (Requests, Responses, Items, and Selectors). However, there are
other cases where the memory leaks could come from other (more or less obscure)
objects. If this is your case, and you can't find your leaks using ``trackref``
you still have another resource: the `Guppy library`_. 

.. _Guppy library: http://pypi.python.org/pypi/guppy

If you use setuptools, you can install Guppy with the following command::

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
which attribute those dicts are referenced you could do::

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

As you can see, the Guppy module is very powerful, but also requires some deep
knowledge about Python internals. For more info about Guppy, refer to the
`Guppy documentation`_.

.. _Guppy documentation: http://guppy-pe.sourceforge.net/

