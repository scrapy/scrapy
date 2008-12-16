.. _install:

=====================
How to install Scrapy
=====================

Requirements
============

* `Python <http://www.python.org>`_ 2.5 or above
* `Twisted <http://twistedmatrix.com>`_
* `libxml2 <http://xmlsoft.org>`_
* `pyopenssl <http://pyopenssl.sourceforge.net>`_

Optional:

* `spidermonkey <http://www.mozilla.org/js/spidermonkey/>`_
* `simplejson <http://code.google.com/p/simplejson/>`_

Install Python
==============

Scrapy works with Python 2.5 or above, you can get it at http://www.python.org.

Install required libraries
==========================

The procedure for installing the required third party libraries (twisted, libxml2 and pyopenssl) depends on the platform and OS you use.

If you're running Ubuntu/Debian Linux do:

.. code-block:: bash

   apt-get install python-twisted python-libxml2 python-pyopenssl

Or in Arch Linux do:

.. code-block:: bash

   pacman -S twisted python-lxml pyopenssl


Install Scrapy code
===================


