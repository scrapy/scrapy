.. _install:

.. highlight:: sh

============
Installation
============

Requirements
============

* `Python <http://www.python.org>`_ 2.5 or 2.6
* `Twisted <http://twistedmatrix.com>`_ 8.0 or above
* `libxml2 <http://xmlsoft.org>`_ (2.6.28 or above recommended)

Optional:

* `pyopenssl <http://pyopenssl.sourceforge.net>`_ (for HTTPS support)
* `spidermonkey <http://www.mozilla.org/js/spidermonkey/>`_ (for Javascript support)

Install Python
==============

Scrapy works with Python 2.5 or 2.6, you can get it at http://www.python.org/download/

Install required libraries
==========================

The procedure for installing the required third party libraries depends on the
platform and operating system you use.

Ubuntu/Debian
-------------

If you're running Ubuntu/Debian Linux run the following command as root::

   $ apt-get install python-twisted python-libxml2 python-pyopenssl

Arch
----

If you are running Arch Linux use the following command to install required dependencies::

   $ pacman -S twisted python-lxml pyopenssl

Windows
-------

1. Get Twisted for Windows here::
   http://twistedmatrix.com/trac/wiki/Downloads
2. Get PyOpenSSL for Windows here::
   http://sourceforge.net/project/showfiles.php?group_id=31249
3. Get libxml2 for Windows here::
   http://users.skynet.be/sbi/libxml-python/

Install Scrapy code
===================

We're working hard to get the first release of Scrapy out. In the meantime,
please download the latest development version from the Subversion_ repository.

.. _Subversion: http://subversion.tigris.org/

To do this, follow this steps:

1. Check out Scrapy code
------------------------

Check out Scrapy code (you will need to have Subversion_ installed)::
   
   $ svn co http://svn.scrapy.org/scrapy/trunk/ scrapy-trunk

2. Add Scrapy to your Python path
---------------------------------

You can do this by making a symbolic link to your system ``site-packages``
directory like this::

   $ ln -s `pwd`/scrapy-trunk/scrapy SITE-PACKAGES/scrapy

Where ``SITE-PACKAGES`` is the location of your system ``site-packages``
directory, to find this out execute the following::

   $ python -c "from distutils.sysconfig import get_python_lib; print get_python_lib()"

Or by adding the ``scrapy-trunk`` directory to your ``PYTHONPATH`` environment
variable, like this::

   $ export PYTHONPATH=`pwd`/scrapy-trunk:$PYTHONPATH

3. Make the scrapy-admin.py script executable
---------------------------------------------

Make the ``scrapy-trunk/scrapy/bin/scrapy-admin.py`` script executable
system-wide. To do this create a symbolic link to the file in a directory on
your sistem path, like::
   
   $ ln -s `pwd`/scrapy-trunk/scrapy/bin/scrapy-admin.py /usr/local/bin

