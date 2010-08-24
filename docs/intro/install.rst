.. _intro-install:

==================
Installation guide
==================

This document describes how to install Scrapy on Linux, Windows and Mac OS X
systems and it consists of the following 3 steps:

* :ref:`intro-install-step1`
* :ref:`intro-install-step2`
* :ref:`intro-install-step3`

If you use Ubuntu (9.10 or above), you can use the :ref:`Ubuntu packages
<topics-ubuntu>` to install Scrapy more easily, skipping these steps. The
Ubuntu packages are also kept updated with latest bug fixes.

.. _intro-install-requirements:

Requirements
============

* `Python`_ 2.5, 2.6, 2.7 (3.x is not yet supported)

* `Twisted`_ 2.5.0, 8.0 or above (Windows users: you'll need to install
  `Zope.Interface`_ and maybe `pywin32`_ because of `this Twisted bug`_)

* `libxml2`_ (versions prior to 2.6.28 are known to have problems parsing certain malformed HTML, and have also been reported to contain leaks, so 2.6.28 or above is highly recommended)

.. _Python: http://www.python.org
.. _Twisted: http://twistedmatrix.com
.. _libxml2: http://xmlsoft.org
.. _pywin32: http://sourceforge.net/projects/pywin32/
.. _Zope.Interface: http://pypi.python.org/pypi/zope.interface#download
.. _this Twisted bug: http://twistedmatrix.com/trac/ticket/3707

Optional:

* `pyopenssl <http://pyopenssl.sourceforge.net>`_ (for HTTPS support, highly recommended)
* `simplejson <http://undefined.org/python/#simplejson>`_ (for (de)serializing JSON)

.. _intro-install-step1:

Step 1. Install Python
======================

Scrapy works with Python 2.5, 2.6 or 2.7, which you can get at http://www.python.org/download/

.. highlight:: sh

.. _intro-install-step2:

Step 2. Install required libraries
==================================

The procedure for installing the required third party libraries depends on the
platform and operating system you use.

Ubuntu/Debian
-------------

If you're running Ubuntu/Debian Linux, run the following command as root::

   apt-get install python-twisted python-libxml2

To install optional libraries::

   apt-get install python-pyopenssl python-simplejson

Arch Linux
----------

If you are running Arch Linux, run the following command as root::

   pacman -S twisted libxml2

To install optional libraries::

   pacman -S pyopenssl python-simplejson

Mac OS X
--------

First, download `Twisted for Mac`_.

.. _Twisted for Mac: http://twistedmatrix.com/trac/wiki/Downloads#MacOSX

Mac OS X ships an ``libxml2`` version too old to be used by Scrapy. Also, by
looking on the web it seems that installing ``libxml2`` on MacOSX is a bit of a
challenge. Here is a way to achieve this, though not acceptable on the long
run:

1. Fetch the following libxml2 and libxslt packages:

   ftp://xmlsoft.org/libxml2/libxml2-2.7.3.tar.gz

   ftp://xmlsoft.org/libxml2/libxslt-1.1.24.tar.gz

2. Extract, build and install them both with::

       ./configure --with-python=/Library/Frameworks/Python.framework/Versions/2.5/
       make
       sudo make install

   Replacing ``/Library/Frameworks/Python.framework/Version/2.5/`` with your
   current python framework location.

3. Install libxml2 Python bidings with::

       cd libxml2-2.7.3/python
       sudo make install

   The libraries and modules should be installed in something like
   /usr/local/lib/python2.5/site-packages. Add it to your ``PYTHONPATH`` and
   you are done.

4. Check the ``libxml2`` library was installed properly with::

       python -c 'import libxml2'

Windows
-------

Download and install:

1. `Twisted for Windows <http://twistedmatrix.com/trac/wiki/Downloads>`_ - you
   may need to install `pywin32`_ because of `this Twisted bug`_

2. Install `Zope.Interface`_ (required by Twisted)

3. `libxml2 for Windows <http://users.skynet.be/sbi/libxml-python/>`_

4. `PyOpenSSL for Windows <http://sourceforge.net/project/showfiles.php?group_id=31249>`_

.. _intro-install-step3:

Step 3. Install Scrapy
======================

There are three ways to download and install Scrapy:

1. :ref:`intro-install-release`
2. :ref:`intro-install-easy`
3. :ref:`intro-install-dev`

.. _intro-install-release:

Installing an official release
------------------------------

Download Scrapy from the `Download page`_. Scrapy is distributed in two ways: a
source code tarball (for Unix and Mac OS X systems) and a Windows installer
(for Windows). If you downloaded the tarball, you can install it as any Python
package using ``setup.py``::

   tar zxf scrapy-X.X.X.tar.gz
   cd scrapy-X.X.X
   python setup.py install

If you downloaded the Windows installer, just run it.

.. warning:: In Windows, you may need to add the ``C:\Python25\Scripts`` (or
   ``C:\Python26\Scripts``) folder to the system path by adding that directory
   to the ``PATH`` environment variable from the `Control Panel`_.

.. _Download page: http://scrapy.org/download/

.. _intro-install-easy:

Installing with `easy_install`_
-------------------------------

You can install Scrapy running `easy_install`_ like this::

   easy_install -U Scrapy

.. _easy_install: http://peak.telecommunity.com/DevCenter/EasyInstall

.. _intro-install-dev:

Installing the development version
-----------------------------------

.. note:: If you use the development version of Scrapy, you should subscribe
   to the mailing lists to get notified of any changes to the API.


1. Check out the latest development code from the `Mercurial`_ repository (you
   need to install `Mercurial_` first)::

      hg clone http://hg.scrapy.org/scrapy scrapy-trunk

.. _Mercurial: http://www.selenic.com/mercurial/

2. Add Scrapy to your Python path

   If you're on Linux, Mac or any Unix-like system, you can make a symbolic link
   to your system ``site-packages`` directory like this::

       ln -s /path/to/scrapy-trunk/scrapy SITE-PACKAGES/scrapy

   Where ``SITE-PACKAGES`` is the location of your system ``site-packages``
   directory. To find this out execute the following::

       python -c "from distutils.sysconfig import get_python_lib; print get_python_lib()"

   Alternatively, you can define your ``PYTHONPATH`` environment variable so that
   it includes the ``scrapy-trunk`` directory. This solution also works on Windows
   systems, which don't support symbolic links.  (Environment variables can be
   defined on Windows systems from the `Control Panel`_).

   Unix-like example::

       PYTHONPATH=/path/to/scrapy-trunk

   Windows example (from command line, but you should probably use the `Control
   Panel`_)::

       set PYTHONPATH=C:\path\to\scrapy-trunk

3. Make the ``scrapy`` command available

   On Unix-like systems, create a symbolic link to the file
   ``scrapy-trunk/bin/scrapy`` in a directory on your system path,
   such as ``/usr/local/bin``. For example::

       ln -s `pwd`/scrapy-trunk/bin/scrapy /usr/local/bin

   This simply lets you type ``scrapy`` from within any directory, rather
   than having to qualify the command with the full path to the file.

   On Windows systems, the same result can be achieved by copying the file
   ``scrapy-trunk/bin/scrapy`` to somewhere on your system path,
   for example ``C:\Python25\Scripts``, which is customary for Python scripts.

.. _Control Panel: http://www.microsoft.com/resources/documentation/windows/xp/all/proddocs/en-us/sysdm_advancd_environmnt_addchange_variable.mspx

