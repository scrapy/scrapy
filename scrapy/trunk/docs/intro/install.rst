.. _intro-install:

============
Installation
============

.. highlight:: sh

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

   apt-get install python-twisted python-libxml2 python-pyopenssl

Arch Linux
----------

If you are running Arch Linux use the following command to install required dependencies::

   pacman -S twisted libxml2 pyopenssl

MacOSX
------

MacOSX ships an libxml2 version too old to be used by Scrapy. Also, by
looking on the web it seems that installing libxml2 on MacOSX is a bit
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
   /usr/local/lib/python2.5/site-packages. Add it to your PYTHONPATH
   and you are done. Check the library is there with a simple::

       python -c 'import libxml2'

Windows
-------

Download and install:

1. `Twisted for Windows <http://twistedmatrix.com/trac/wiki/Downloads>`_
2. `PyOpenSSL for Windows <http://sourceforge.net/project/showfiles.php?group_id=31249>`_
3. `libxml2 for Windows <http://users.skynet.be/sbi/libxml-python/>`_

Install Scrapy code
===================

We're working hard to get the first release of Scrapy out. In the meantime,
please download the latest development version from the Subversion_ repository.

.. _Subversion: http://subversion.tigris.org/

To do this, follow this steps:

1. Check out Scrapy code (you will need to have Subversion_ installed)::
   
      svn co http://svn.scrapy.org/scrapy/trunk/ scrapy-trunk

2. Add Scrapy to your Python path:

   You can do this by making a symbolic link to your system ``site-packages``
   directory like this::

      ln -s `pwd`/scrapy-trunk/scrapy SITE-PACKAGES/scrapy

   Where ``SITE-PACKAGES`` is the location of your system ``site-packages``
   directory, to find this out execute the following::

      python -c "from distutils.sysconfig import get_python_lib; print get_python_lib()"

   Or by adding the ``scrapy-trunk`` directory to your ``PYTHONPATH`` environment
   variable, like this::

      export PYTHONPATH=`pwd`/scrapy-trunk:$PYTHONPATH

3. Make the ``scrapy-trunk/scrapy/bin/scrapy-admin.py`` script executable
   system-wide. To do this create a symbolic link to the file in a directory on
   your sistem path, like::
   
      ln -s `pwd`/scrapy-trunk/scrapy/bin/scrapy-admin.py /usr/local/bin

