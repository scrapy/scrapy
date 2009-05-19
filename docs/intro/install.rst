.. _intro-install:

==================
Installation guide
==================

This document describes how to install Scrapy in Linux, Windows and Mac OS X
systems and it consists on the following 3 steps:

* :ref:`intro-install-step1`
* :ref:`intro-install-step2`
* :ref:`intro-install-step3`

.. _intro-install-requirements:

Requirements
============

* `Python`_ 2.5 or 2.6 (3.x is not yet supported)

* `Twisted`_ 2.5.0, 8.0 or above (Windows users: you may need to install
  `pywin32`_ because of `this Twisted bug`_)

* `libxml2`_ (2.6.28 or above is recommended)

.. _Python: http://www.python.org
.. _Twisted: http://twistedmatrix.com
.. _libxml2: http://xmlsoft.org
.. _pywin32: http://sourceforge.net/projects/pywin32/
.. _this Twisted bug: http://twistedmatrix.com/trac/ticket/3707

Optional:

* `pyopenssl <http://pyopenssl.sourceforge.net>`_ (for HTTPS support, highly recommended)
* `spidermonkey <http://www.mozilla.org/js/spidermonkey/>`_ (for parsing Javascript)

.. _intro-install-step1:

Step 1. Install Python
======================

Scrapy works with Python 2.5 or 2.6, you can get it at http://www.python.org/download/

.. highlight:: sh

.. _intro-install-step2:

Step 2. Install required libraries
==================================

The procedure for installing the required third party libraries depends on the
platform and operating system you use.

Ubuntu/Debian
-------------

If you're running Ubuntu/Debian Linux run the following command as root::

   apt-get install python-twisted python-libxml2

To install optional libraries::

   apt-get install python-pyopenssl spidermonkey-bin

Arch Linux
----------

If you are running Arch Linux run the following command as root::

   pacman -S twisted libxml2

To install optional libraries::

   pacman -S pyopenssl spidermonkey

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

4. Check the ``libxml2`` library was installed propertly with::

       python -c 'import libxml2'

Windows
-------

Download and install:

1. `Twisted for Windows <http://twistedmatrix.com/trac/wiki/Downloads>`_ - you
   may need to install `pywin32`_ because of `this Twisted bug`_

2. `libxml2 for Windows <http://users.skynet.be/sbi/libxml-python/>`_

3. `PyOpenSSL for Windows <http://sourceforge.net/project/showfiles.php?group_id=31249>`_

.. _intro-install-step3:

Step 3. Install Scrapy
======================

We're working hard to get the first release of Scrapy out. In the meantime,
please download the latest development version from the `Mercurial`_
repository.

.. _Mercurial: http://www.selenic.com/mercurial/

Just follow these steps:

3.1. Install Mercurial
-----------------------

Make sure that you have `Mercurial`_ installed, and that you can run its
commands from a shell. (Enter ``hg help`` at a shell prompt to test this.)

3.2. Check out the Scrapy source code
-------------------------------------

By running the following command::

    hg clone http://hg.scrapy.org/scrapy scrapy-trunk

3.3. Install the Scrapy module
------------------------------

Install the Scrapy module by running the following commands::

    cd scrapy-trunk
    python setup.py install

If you're on Unix-like systems (Linux, Mac, etc) you may need to run the second
command with root privileges, for example by running::

    sudo python setup.py install

.. warning:: In Windows, you may need to add the ``C:\Python25\Scripts`` folder
   to the system path by adding that directory to the ``PATH`` environment
   variable from the `Control Panel`_.

.. warning:: Keep in mind that Scrapy is still being changed, as we haven't yet
   released the first stable version. So it's important that you keep updating
   the code periodically and reinstalling the Scrapy module. A more convenient
   way is to use Scrapy module without installing it (see below).

Use Scrapy without installing it
================================

Another alternative is to use the Scrapy module without installing it which
makes it easier to keep using the last Development code without having to
reinstall it everytime you do a ``hg pull -u``.

You can do this by following the next steps:

Add Scrapy to your Python path
------------------------------

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

Make the scrapy-admin.py script available
-----------------------------------------

On Unix-like systems, create a symbolic link to the file
``scrapy-trunk/scrapy/bin/scrapy-admin.py`` in a directory on your system path,
such as ``/usr/local/bin``. For example::

    ln -s `pwd`/scrapy-trunk/scrapy/bin/scrapy-admin.py /usr/local/bin

This simply lets you type scrapy-admin.py from within any directory, rather
than having to qualify the command with the full path to the file.

On Windows systems, the same result can be achieved by copying the file
``scrapy-trunk/scrapy/bin/scrapy-admin.py`` to somewhere on your system path,
for example ``C:\Python25\Scripts``, which is customary for Python scripts.

.. _Control Panel: http://www.microsoft.com/resources/documentation/windows/xp/all/proddocs/en-us/sysdm_advancd_environmnt_addchange_variable.mspx

