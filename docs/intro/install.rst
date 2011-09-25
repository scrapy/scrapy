.. _intro-install:

==================
Installation guide
==================

This document describes how to install Scrapy on Linux, Windows and Mac OS X.

.. _intro-install-requirements:

Requirements
============

* `Python`_ 2.5, 2.6, 2.7 (3.x is not yet supported)

* `Twisted`_ 2.5.0, 8.0 or above (Windows users: you'll need to install
  `Zope.Interface`_ and maybe `pywin32`_ because of `this Twisted bug`_)

* `w3lib`_

* `lxml`_ or `libxml2`_ (if using `libxml2`_, version 2.6.28 or above is highly recommended)

* `simplejson`_ (not required if using Python 2.6 or above)

* `pyopenssl <http://pyopenssl.sourceforge.net>`_ (for HTTPS support. Optional,
  but highly recommended)

.. _intro-install-python:

Install Python
==============

First, you need to install Python, if you haven't done so already.

Scrapy works with Python 2.5, 2.6 or 2.7, which you can get at
http://www.python.org/download/

.. seealso:: :ref:`faq-python-versions`

.. highlight:: sh

.. _intro-install-scrapy:

Install Scrapy
==============

There are many ways to install Scrapy. Pick the one you feel more comfortable
with.

* :ref:`intro-install-release` (requires installing dependencies separately)
* :ref:`intro-install-easy` (automatically installs dependencies)
* :ref:`intro-install-pip` (automatically installs dependencies)

.. _intro-install-release:

Download and install an official release
----------------------------------------

Download Scrapy from the `Download page`_. Scrapy is distributed in two ways: a
source code tarball (for Unix and Mac OS X systems) and a Windows installer
(for Windows). If you downloaded the tarball, you can install it as any Python
package using ``setup.py``::

   tar zxf Scrapy-X.X.X.tar.gz
   cd Scrapy-X.X.X
   python setup.py install

If you downloaded the Windows installer, just run it.

.. warning:: In Windows, you may need to add the ``C:\Python25\Scripts`` (or
   ``C:\Python26\Scripts``) folder to the system path by adding that directory
   to the ``PATH`` environment variable from the `Control Panel`_.

.. _Download page: http://scrapy.org/download/

.. _intro-install-easy:

Installing with ``easy_install``
--------------------------------

You can install Scrapy using setuptools_'s ``easy_install`` with::

   easy_install -U Scrapy

.. _intro-install-pip:

Installing with `pip`_
----------------------

You can install Scrapy using `pip`_ with::

   pip install Scrapy

.. _intro-install-platforms:

Platform specific instructions
==============================

Linux
-----

Ubuntu 9.10 or above
~~~~~~~~~~~~~~~~~~~~

If you're running Ubuntu 9.10 (or above), use the official :ref:`Ubuntu
Packages <topics-ubuntu>`, which already solve all dependencies for you and are
continuously updated with  the latest bug fixes.

Debian or Ubuntu (9.04 or older)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you're running Debian Linux, run the following command as root::

   apt-get install python-twisted python-libxml2 python-pyopenssl python-simplejson

Then::

    easy_install -U w3lib

And then follow the instructions in :ref:`intro-install-scrapy`.

Arch Linux
~~~~~~~~~~

If you are running Arch Linux, run the following command as root::

   pacman -S twisted libxml2 pyopenssl python-simplejson

Then::

    easy_install -U w3lib

And then follow the instructions in :ref:`intro-install-scrapy`.

Other Linux distros
~~~~~~~~~~~~~~~~~~~

The easiest way to install Scrapy in other Linux distros is through
``easy_install``, which will automatically install Twisted, w3lib and lxml as
dependencies. See :ref:`intro-install-easy`.

Another way would be to install dependencies, if you know the packages in your
distros that meets them. See :ref:`intro-install-requirements`.

Mac OS X
--------

The easiest way to install Scrapy on Mac is through ``easy_install`` or
``pip``, which will automatically install Twisted, w3lib and lxml dependencies.

See :ref:`intro-install-easy`.

Windows
-------

There are two ways to install Scrapy in Windows:

* using ``easy_install`` or ``pip`` - see :ref:`intro-install-easy` or
  :ref:`intro-install-pip`

* using the Windows installer, but you need to download and install the
  dependencies manually:

  1. `Twisted for Windows <http://twistedmatrix.com/trac/wiki/Downloads>`_ - you
     may need to install `pywin32`_ because of `this Twisted bug`_

  2. Install `Zope.Interface`_ (required by Twisted)

  3. `libxml2 for Windows <http://users.skynet.be/sbi/libxml-python/>`_

  4. `PyOpenSSL for Windows <http://sourceforge.net/project/showfiles.php?group_id=31249>`_

  5. Download the Windows installer from the `Downloads page`_ and install it.

.. _Python: http://www.python.org
.. _Twisted: http://twistedmatrix.com
.. _w3lib: http://pypi.python.org/pypi/w3lib
.. _lxml: http://codespeak.net/lxml/
.. _libxml2: http://xmlsoft.org
.. _pywin32: http://sourceforge.net/projects/pywin32/
.. _simplejson: http://pypi.python.org/pypi/simplejson/
.. _Zope.Interface: http://pypi.python.org/pypi/zope.interface#download
.. _this Twisted bug: http://twistedmatrix.com/trac/ticket/3707
.. _pip: http://pypi.python.org/pypi/pip
.. _setuptools: http://pypi.python.org/pypi/setuptools
.. _Control Panel: http://www.microsoft.com/resources/documentation/windows/xp/all/proddocs/en-us/sysdm_advancd_environmnt_addchange_variable.mspx
.. _Downloads page: http://scrapy.org/download/
