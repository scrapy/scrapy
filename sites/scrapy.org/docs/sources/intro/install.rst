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

We're working hard to get the first release of Scrapy out. In the meantime, please download the latest development version from the Subversion_ repository.

To do this, follow this steps:

1. Check out Scrapy code (you will need to have Subversion_ installed):
   
   .. code-block:: bash

      svn co http://svn.scrapy.org/scrapy/trunk/ scrapy-trunk

2. Add Scrapy to your Python path. You can do this by making a symbolic link to your system ``site-packages`` directory like this:  

   .. code-block:: bash

      ln -s `pwd`/scrapy-trunk/scrapy SITE-PACKAGES/scrapy

   Where ``SITE-PACKAGES`` is the location of your system ``site-packages`` directory, to find this out execute the following:

   .. code-block:: bash

      python -c "from distutils.sysconfig import get_python_lib; print get_python_lib()"


   Or by adding the ``scrapy-trunk`` directory to your ``PYTHONPATH`` environment variable, like this:

   .. code-block:: bash

      export PYTHONPATH=`pwd`/scrapy-trunk:PYTHONPATH


3. Make the ``scrapy-trunk/scrapy/bin/scrapy-admin.py`` script executable system-wide. To do this create a symbolic link to the file in a directory on your sistem path, like:
   
   .. code-block:: bash

       ln -s `pwd`/scrapy-trunk/scrapy/bin/scrapy-admin.py /usr/local/bin

.. _Subversion: http://subversion.tigris.org/
