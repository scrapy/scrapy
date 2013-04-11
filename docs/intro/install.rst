.. _intro-install:

==================
Installation guide
==================

Pre-requisites
==============

The installation steps assume that you have the following things installed:

* Python 2.6 or 2.7
* OpenSSL. This comes preinstalled in all operating systems except Windows (see :ref:`intro-install-platform-notes`)
* `pip`_ or `easy_install`_ Python package managers

Installing Scrapy
=================

You can install Scrapy using easy_install or pip (which is the canonical way to
distribute and install Python packages).

.. note:: Check :ref:`intro-install-platform-notes` first.

To install using pip::

   pip install Scrapy

To install using easy_install::

   easy_install Scrapy

.. _intro-install-platform-notes:

Platform specific installation notes
====================================

Windows
-------

After installing Python, follow these steps before installing Scrapy:

* add the ``C:\python27\Scripts`` and ``C:\python27`` folders to the system
  path by adding those directories to the ``PATH`` environment variable from
  the `Control Panel`_.

* install OpenSSL by following these steps:

  1. go to `Win32 OpenSSL page <http://slproweb.com/products/Win32OpenSSL.html>`_

  2. download Visual C++ 2008 redistributables for your Windows and architecture

  3. download OpenSSL for your Windows and architecture (the regular version, not the light one)

  4. add the ``c:\openssl-win32\bin`` (or similar) directory to your ``PATH``, the same way you added ``python27`` in the first step`` in the first step

* some binary packages that Scrapy depends on (like Twisted, lxml and pyOpenSSL) require a compiler available to install, and fail if you don't have Visual Studio installed. You can find Windows installers for those in the following links. Make sure you respect your Python version and Windows architecture.

  * pywin32: http://sourceforge.net/projects/pywin32/files/
  * Twisted: http://twistedmatrix.com/trac/wiki/Downloads
  * zope.interface: download the egg from `zope.interface pypi page <http://pypi.python.org/pypi/zope.interface>`_ and install it by running ``easy_install file.egg``
  * lxml: http://pypi.python.org/pypi/lxml/
  * pyOpenSSL: https://launchpad.net/pyopenssl

Finally, this page contains many precompiled Python binary libraries, which may
come handy to fulfill Scrapy dependencies:

    http://www.lfd.uci.edu/~gohlke/pythonlibs/

Ubuntu 9.10 or above
~~~~~~~~~~~~~~~~~~~~

**Don't** use the ``python-scrapy`` package provided by Ubuntu, they are
typically too old and slow to catch up with latest Scrapy.

Instead, use the official :ref:`Ubuntu Packages <topics-ubuntu>`, which already
solve all dependencies for you and are continuously updated with the latest bug
fixes.

.. _Python: http://www.python.org
.. _pywin32: http://sourceforge.net/projects/pywin32/
.. _this Twisted bug: http://twistedmatrix.com/trac/ticket/3707
.. _pip: http://www.pip-installer.org/en/latest/installing.html
.. _easy_install: http://pypi.python.org/pypi/setuptools
.. _Control Panel: http://www.microsoft.com/resources/documentation/windows/xp/all/proddocs/en-us/sysdm_advancd_environmnt_addchange_variable.mspx
