.. _faq:

Frequently Asked Questions
==========================

How does Scrapy compare to BeatifulSoul or lxml?
------------------------------------------------

`BeautifulSoup`_ and `lxml`_ are libraries for parsing HTML and XML. Scrapy is
an application framework for writing web spiders that crawl web sites and
extract data from it. Scrapy provides some mechanisms for extracting data
(called selectors) but you can easily use `BeautifulSoup`_ or `lxml`_ if you
feel more comfortable with them. After all, they're just parsing libraries
which can be imported and used from any Python code.

To illustrate from another point of view, comparing `BeautifulSoup`_ or `lxml`_
to Scrapy is like comparing `urllib`_ or `urlparse`_ to `Django`_ (a popular
Python web framework).

.. _BeautifulSoup: http://www.crummy.com/software/BeautifulSoup/
.. _lxml: http://codespeak.net/lxml/
.. _urllib: http://docs.python.org/library/urllib.html
.. _urlparse: http://docs.python.org/library/urlparse.html
.. _Django: http://www.djangoproject.com

Does Scrapy work in Python 3.0?
-------------------------------

No, and there are no ongoing plans to port Scrapy to Python 3.0 yet. At the
moment Scrapy requires Python 2.5 or 2.6 to work.

