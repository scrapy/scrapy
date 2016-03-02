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
  installs `setuptools`_ if not installed. Python 2.7.9 and later include
  `pip`_ by default, so you may have it already.

* `lxml`_. Most Linux distributions ships prepackaged versions of lxml.
  Otherwise refer to http://lxml.de/installation.html

* `OpenSSL`_. This comes preinstalled in all operating systems, except Windows
  where the Python installer ships it bundled.

You can install Scrapy using pip (which is the canonical way to install Python
packages). To install using ``pip`` run::

   pip install Scrapy

.. _intro-install-platform-notes:

Platform specific installation notes
====================================

Anaconda
--------

.. note::

  For Windows users, or if you have issues installing through `pip`, this is
  the recommended way to install Scrapy.

If you already have installed `Anaconda`_ or `Miniconda`_, the company
`Scrapinghub`_ maintains official conda packages for Linux, Windows and OS X.

To install Scrapy using ``conda``, run::

  conda install -c scrapinghub scrapy 


Windows
-------

* Install Python 2.7 from https://www.python.org/downloads/

  You need to adjust ``PATH`` environment variable to include paths to
  the Python executable and additional scripts. The following paths need to be
  added to ``PATH``::

      C:\Python27\;C:\Python27\Scripts\;

  To update the ``PATH`` open a Command prompt and run::

      c:\python27\python.exe c:\python27\tools\scripts\win_add2path.py

  Close the command prompt window and reopen it so changes take effect, run the
  following command and check it shows the expected Python version::

      python --version

* Install `pywin32` from http://sourceforge.net/projects/pywin32/

  Be sure you download the architecture (win32 or amd64) that matches your system

* *(Only required for Python<2.7.9)* Install `pip`_ from
  https://pip.pypa.io/en/latest/installing/

  Now open a Command prompt to check ``pip`` is installed correctly:: 

      pip --version

* At this point Python 2.7 and ``pip`` package manager must be working, let's
  install Scrapy::

      pip install Scrapy

Ubuntu 9.10 or above
--------------------

**Don't** use the ``python-scrapy`` package provided by Ubuntu, they are
typically too old and slow to catch up with latest Scrapy.

Instead, use the official :ref:`Ubuntu Packages <topics-ubuntu>`, which already
solve all dependencies for you and are continuously updated with the latest bug
fixes.

If you prefer to build the python dependencies locally instead of relying on
system packages you'll need to install their required non-python dependencies
first::

    sudo apt-get install python-dev python-pip libxml2-dev libxslt1-dev zlib1g-dev libffi-dev libssl-dev

You can install Scrapy with ``pip`` after that::

    pip install Scrapy

.. note::

    The same non-python dependencies can be used to install Scrapy in Debian
    Wheezy (7.0) and above.

Archlinux
---------

You can follow the generic instructions or install Scrapy from `AUR Scrapy package`::

    yaourt -S scrapy

Mac OS X
--------

Building Scrapy's dependencies requires the presence of a C compiler and
development headers. On OS X this is typically provided by Apple’s Xcode
development tools. To install the Xcode command line tools open a terminal
window and run::

    xcode-select --install

There's a `known issue <https://github.com/pypa/pip/issues/2468>`_ that
prevents ``pip`` from updating system packages. This has to be addressed to
successfully install Scrapy and its dependencies. Here are some proposed
solutions:

* *(Recommended)* **Don't** use system python, install a new, updated version
  that doesn't conflict with the rest of your system. Here's how to do it using
  the `homebrew`_ package manager:

  * Install `homebrew`_ following the instructions in http://brew.sh/

  * Update your ``PATH`` variable to state that homebrew packages should be
    used before system packages (Change ``.bashrc`` to ``.zshrc`` accordantly
    if you're using `zsh`_ as default shell)::

      echo "export PATH=/usr/local/bin:/usr/local/sbin:$PATH" >> ~/.bashrc

  * Reload ``.bashrc`` to ensure the changes have taken place::

      source ~/.bashrc

  * Install python::

      brew install python

  * Latest versions of python have ``pip`` bundled with them so you won't need
    to install it separately. If this is not the case, upgrade python::

      brew update; brew upgrade python

* *(Optional)* Install Scrapy inside an isolated python environment.

  This method is a workaround for the above OS X issue, but it's an overall
  good practice for managing dependencies and can complement the first method.

  `virtualenv`_ is a tool you can use to create virtual environments in python.
  We recommended reading a tutorial like
  http://docs.python-guide.org/en/latest/dev/virtualenvs/ to get started.

After any of these workarounds you should be able to install Scrapy::

  pip install Scrapy

.. _Python: https://www.python.org/
.. _pip: https://pip.pypa.io/en/latest/installing/
.. _easy_install: https://pypi.python.org/pypi/setuptools
.. _Control Panel: https://www.microsoft.com/resources/documentation/windows/xp/all/proddocs/en-us/sysdm_advancd_environmnt_addchange_variable.mspx
.. _lxml: http://lxml.de/
.. _OpenSSL: https://pypi.python.org/pypi/pyOpenSSL
.. _setuptools: https://pypi.python.org/pypi/setuptools
.. _AUR Scrapy package: https://aur.archlinux.org/packages/scrapy/
.. _homebrew: http://brew.sh/
.. _zsh: http://www.zsh.org/
.. _virtualenv: https://virtualenv.pypa.io/en/latest/
.. _Scrapinghub: http://scrapinghub.com
.. _Anaconda: http://docs.continuum.io/anaconda/index
.. _Miniconda: http://conda.pydata.org/docs/install/quick.html
