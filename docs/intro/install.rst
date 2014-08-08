.. _intro-install:

==================
Installation guide
==================

Installing Scrapy
=================

.. note:: Check :ref:`intro-install-platform-notes` first.

The installation steps assume that you have the following things installed:

* `Python`_ 2.7

* `pip`_ and `setuptools`_ Python packages. Nowadays `pip`_ requires and
  installs `setuptools`_ if not installed.

* `lxml`_. Most Linux distributions ships prepackaged versions of lxml.
  Otherwise refer to http://lxml.de/installation.html

* `OpenSSL`_. This comes preinstalled in all operating systems, except Windows
  where the Python installer ships it bundled.

You can install Scrapy using pip (which is the canonical way to install Python
packages).

To install using pip::

   pip install Scrapy

.. _intro-install-platform-notes:

Platform specific installation notes
====================================

Windows
-------

* Install Python 2.7 from http://python.org/download/

  You need to adjust ``PATH`` environment variable to include paths to
  the Python executable and additional scripts. The following paths need to be
  added to ``PATH``::

      C:\Python2.7\;C:\Python2.7\Scripts\;

  To update the ``PATH`` open a Command prompt and run::

      c:\python27\python.exe c:\python27\tools\scripts\win_add2path.py

  Close the command prompt window and reopen it so changes take effect, run the
  following command and check it shows the expected Python version::

      python --version

* Install `pip`_ from https://pip.pypa.io/en/latest/installing.html

  Now open a Command prompt to check ``pip`` is installed correctly:: 

      pip --version

* At this point Python 2.7 and ``pip`` package manager must be working, let's
  install Scrapy::

      pip install Scrapy

Ubuntu 9.10 or above
~~~~~~~~~~~~~~~~~~~~

**Don't** use the ``python-scrapy`` package provided by Ubuntu, they are
typically too old and slow to catch up with latest Scrapy.

Instead, use the official :ref:`Ubuntu Packages <topics-ubuntu>`, which already
solve all dependencies for you and are continuously updated with the latest bug
fixes.

Archlinux
~~~~~~~~~

You can follow the generic instructions or install Scrapy from `AUR Scrapy package`::

    yaourt -S scrapy


.. _Python: http://www.python.org
.. _pip: http://www.pip-installer.org/en/latest/installing.html
.. _easy_install: http://pypi.python.org/pypi/setuptools
.. _Control Panel: http://www.microsoft.com/resources/documentation/windows/xp/all/proddocs/en-us/sysdm_advancd_environmnt_addchange_variable.mspx
.. _lxml: http://lxml.de/
.. _OpenSSL: https://pypi.python.org/pypi/pyOpenSSL
.. _setuptools: https://pypi.python.org/pypi/setuptools
.. _AUR Scrapy package: https://aur.archlinux.org/packages/scrapy/
