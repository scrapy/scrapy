.. _intro-install:

==================
Installation guide
==================

This document describes how to install Scrapy in Linux, Windows and Mac OS X
systems and it consists on the following 3 big steps:

1. Install Python
2. Install required libraries
3. Install Scrapy


.. highlight:: sh

Requirements
============

* `Python <http://www.python.org>`_ 2.5 or 2.6

* `Twisted <http://twistedmatrix.com>`_ 2.5.0, 8.0 or above (Windows users: you
  may need to install `pywin32`_ because of `this Twisted bug`_)

* `libxml2 <http://xmlsoft.org>`_ (2.6.28 or above recommended)

Optional:

* `pyopenssl <http://pyopenssl.sourceforge.net>`_ (for HTTPS support)
* `spidermonkey <http://www.mozilla.org/js/spidermonkey/>`_ (for Javascript support)

1. Install Python
=================

Scrapy works with Python 2.5 or 2.6, you can get it at http://www.python.org/download/

2. Install required libraries
=============================

The procedure for installing the required third party libraries depends on the
platform and operating system you use.

Ubuntu/Debian
-------------

If you're running Ubuntu/Debian Linux run the following command as root::

   apt-get install python-twisted python-libxml2 python-pyopenssl

Arch Linux
----------

If you are running Arch Linux run the following command as root::

   pacman -S twisted libxml2 pyopenssl

MacOSX
------

MacOSX ships an ``libxml2`` version too old to be used by Scrapy. Also, by
looking on the web it seems that installing ``libxml2`` on MacOSX is a bit
of a challenge. Here is a way to achieve this, though not acceptable
on the long run:

1. Fetch the following libxml2 and libxslt packages:

   ftp://xmlsoft.org/libxml2/libxml2-2.7.3.tar.gz

   ftp://xmlsoft.org/libxml2/libxslt-1.1.24.tar.gz

2. Extract them, and make every one of them like::

       ./configure --with-python=/Library/Frameworks/Python.framework/Versions/2.5/
       make
       sudo make install
   
referencing your current python framework.

3. In libxml2-2.7.3/python, run::

       sudo make install

   The libraries and modules should be installed in something like
   /usr/local/lib/python2.5/site-packages. Add it to your ``PYTHONPATH``
   and you are done. Check the library is there with a simple::

       python -c 'import libxml2'

Windows
-------

Download and install:

1. `Twisted for Windows <http://twistedmatrix.com/trac/wiki/Downloads>`_ - you may need to install `pywin32`_ because of `this Twisted bug`_
2. `PyOpenSSL for Windows <http://sourceforge.net/project/showfiles.php?group_id=31249>`_
3. `libxml2 for Windows <http://users.skynet.be/sbi/libxml-python/>`_

.. _pywin32: http://sourceforge.net/projects/pywin32/
.. _this Twisted bug: http://twistedmatrix.com/trac/ticket/3707

3. Install Scrapy
=================

We're working hard to get the first release of Scrapy out. In the meantime,
please download the latest development version from the Subversion_ repository.

.. _Subversion: http://subversion.tigris.org/

Just follow these steps:

3.1. Install Subversion
-----------------------

Make sure that you have `Subversion`_ installed, and that you can run its
commands from a shell. (Enter ``svn help`` at a shell prompt to test this.)

3.2. Check out the Scrapy source code
-------------------------------------

By running the following command::
   
    svn checkout http://svn.scrapy.org/scrapy/trunk/ scrapy-trunk

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
   the Subversion code periodically and reinstalling the Scrapy module. A more
   convenient way is to use Scrapy module without installing it (see below).

Use Scrapy without installing it
================================

Another alternative is to use the Scrapy module without installing it which
makes it easier to keep using the last Subversion code without having to
reinstall it everytime you do a ``svn update``.

You can do this by following the next steps:

1. Add Scrapy to your Python path
---------------------------------

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

4. Make the scrapy-admin.py script available
--------------------------------------------

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

