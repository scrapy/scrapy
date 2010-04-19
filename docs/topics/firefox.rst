.. _topics-firefox:

==========================
Using Firefox for scraping
==========================

Here is a list of tips and advice on using Firefox for scraping, along with a
list of useful Firefox add-ons to ease the scraping process.

.. _topics-firefox-livedom:

Caveats with inspecting the live browser DOM
============================================

Since Firefox add-ons operate on a live browser DOM, what you'll actually see
when inspecting the page source is not the original HTML, but a modified one
after applying some browser clean up and executing Javascript code.  Firefox,
in particular, is known for adding ``<tbody>`` elements to tables.  Scrapy, on
the other hand, does not modify the original page HTML, so you won't be able to
extract any data if you use ``<tbody`` in your XPath expressions. 

Therefore, you should keep in mind the following things when working with
Firefox and XPath:

* Disable Firefox Javascript while inspecting the DOM looking for XPaths to be
  used in Scrapy

* Never use full XPath paths, use relative and clever ones based on attributes
  (such as ``id``, ``class``, ``width``, etc) or any identifying features like
  ``contains(@href, 'image')``.

* Never include ``<tbody>`` elements in your XPath expressions unless you
  really know what you're doing

.. _topics-firefox-addons:

Useful Firefox add-ons for scraping
===================================

Firebug
-------

`Firebug`_ is a widely known tool among web developers and it's also very
useful for scraping. In particular, its `Inspect Element`_ feature comes very
handy when you need to construct the XPaths for extracting data because it
allows you to view the HTML code of each page element while moving your mouse
over it.

See :ref:`topics-firebug` for a detailed guide on how to use Firebug with
Scrapy.

XPather
-------

`XPather`_ allows you to test XPath expressions directly on the pages.

XPath Checker
-------------

`XPath Checker`_ is another Firefox add-on for testing XPaths on your pages.

Tamper Data
-----------

`Tamper Data`_ is a Firefox add-on which allows you to view and modify the HTTP
request headers sent by Firefox. Firebug also allows to view HTTP headers, but
not to modify them.

Firecookie
----------

`Firecookie`_ makes it easier to view and manage cookies. You can use this
extension to create a new cookie, delete existing cookies, see a list of cookies
for the current site, manage cookies permissions and a lot more. 

.. _Firebug: http://getfirebug.com
.. _Inspect Element: http://www.youtube.com/watch?v=-pT_pDe54aA
.. _XPather: https://addons.mozilla.org/firefox/addon/1192 
.. _XPath Checker: https://addons.mozilla.org/firefox/addon/1095
.. _Tamper Data: http://addons.mozilla.org/firefox/addon/966
.. _Firecookie: https://addons.mozilla.org/firefox/addon/6683

