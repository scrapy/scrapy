.. _intro-install:

==================
Installation guide
==================

.. _faq-python-versions:

Supported Python versions
=========================

Scrapy requires Python 3.7+, either the CPython implementation (default) or
the PyPy implementation (see :ref:`python:implementations`).

.. _intro-install-scrapy:

Installing Scrapy
=================

If you're using `Anaconda`_ or `Miniconda`_, you can install the package from
the `conda-forge`_ channel, which has up-to-date packages for Linux, Windows
and macOS.

To install Scrapy using ``conda``, run::

  conda install -c conda-forge scrapy

Alternatively, if you’re already familiar with installation of Python packages,
you can install Scrapy and its dependencies from PyPI with::

    pip install Scrapy

We strongly recommend that you install Scrapy in :ref:`a dedicated virtualenv <intro-using-virtualenv>`,
to avoid conflicting with your system packages.

Note that sometimes this may require solving compilation issues for some Scrapy
dependencies depending on your operating system, so be sure to check the
:ref:`intro-install-platform-notes`.

For more detailed and platform specifics instructions, as well as
troubleshooting information, read on.


Things that are good to know
----------------------------

Scrapy is written in pure Python and depends on a few key Python packages (among others):

* `lxml`_, an efficient XML and HTML parser
* `parsel`_, an HTML/XML data extraction library written on top of lxml,
* `w3lib`_, a multi-purpose helper for dealing with URLs and web page encodings
* `twisted`_, an asynchronous networking framework
* `cryptography`_ and `pyOpenSSL`_, to deal with various network-level security needs

Some of these packages themselves depend on non-Python packages
that might require additional installation steps depending on your platform.
Please check :ref:`platform-specific guides below <intro-install-platform-notes>`.

In case of any trouble related to these dependencies,
please refer to their respective installation instructions:

* `lxml installation`_
* :doc:`cryptography installation <cryptography:installation>`

.. _lxml installation: https://lxml.de/installation.html


.. _intro-using-virtualenv:

Using a virtual environment (recommended)
-----------------------------------------

TL;DR: We recommend installing Scrapy inside a virtual environment
on all platforms.

Python packages can be installed either globally (a.k.a system wide),
or in user-space. We do not recommend installing Scrapy system wide.

Instead, we recommend that you install Scrapy within a so-called
"virtual environment" (:mod:`venv`).
Virtual environments allow you to not conflict with already-installed Python
system packages (which could break some of your system tools and scripts),
and still install packages normally with ``pip`` (without ``sudo`` and the likes).

See :ref:`tut-venv` on how to create your virtual environment.

Once you have created a virtual environment, you can install Scrapy inside it with ``pip``,
just like any other Python package.
(See :ref:`platform-specific guides <intro-install-platform-notes>`
below for non-Python dependencies that you may need to install beforehand).


.. _intro-install-platform-notes:

Platform specific installation notes
====================================

.. _intro-install-windows:

Windows
-------

Though it's possible to install Scrapy on Windows using pip, we recommend you
to install `Anaconda`_ or `Miniconda`_ and use the package from the
`conda-forge`_ channel, which will avoid most installation issues.

Once you've installed `Anaconda`_ or `Miniconda`_, install Scrapy with::

  conda install -c conda-forge scrapy

To install Scrapy on Windows using ``pip``:

.. warning::
    This installation method requires “Microsoft Visual C++” for installing some 
    Scrapy dependencies, which demands significantly more disk space than Anaconda.

#. Download and execute `Microsoft C++ Build Tools`_ to install the Visual Studio Installer.

#. Run the Visual Studio Installer.

#. Under the Workloads section, select **C++ build tools**.

#. Check the installation details and make sure following packages are selected as optional components:

    * **MSVC**  (e.g MSVC v142 - VS 2019 C++ x64/x86 build tools (v14.23) )
    
    * **Windows SDK**  (e.g Windows 10 SDK (10.0.18362.0))

#. Install the Visual Studio Build Tools.

Now, you should be able to :ref:`install Scrapy <intro-install-scrapy>` using ``pip``.

.. _intro-install-ubuntu:

Ubuntu 14.04 or above
---------------------

Scrapy is currently tested with recent-enough versions of lxml,
twisted and pyOpenSSL, and is compatible with recent Ubuntu distributions.
But it should support older versions of Ubuntu too, like Ubuntu 14.04,
albeit with potential issues with TLS connections.

**Don't** use the ``python-scrapy`` package provided by Ubuntu, they are
typically too old and slow to catch up with latest Scrapy.


To install Scrapy on Ubuntu (or Ubuntu-based) systems, you need to install
these dependencies::

    sudo apt-get install python3 python3-dev python3-pip libxml2-dev libxslt1-dev zlib1g-dev libffi-dev libssl-dev

- ``python3-dev``, ``zlib1g-dev``, ``libxml2-dev`` and ``libxslt1-dev``
  are required for ``lxml``
- ``libssl-dev`` and ``libffi-dev`` are required for ``cryptography``

Inside a :ref:`virtualenv <intro-using-virtualenv>`,
you can install Scrapy with ``pip`` after that::

    pip install scrapy

.. note::
    The same non-Python dependencies can be used to install Scrapy in Debian
    Jessie (8.0) and above.


.. _intro-install-macos:

macOS
-----

Building Scrapy's dependencies requires the presence of a C compiler and
development headers. On macOS this is typically provided by Apple’s Xcode
development tools. To install the Xcode command line tools open a terminal
window and run::

    xcode-select --install

There's a `known issue <https://github.com/pypa/pip/issues/2468>`_ that
prevents ``pip`` from updating system packages. This has to be addressed to
successfully install Scrapy and its dependencies. Here are some proposed
solutions:

* *(Recommended)* **Don't** use system Python. Install a new, updated version
  that doesn't conflict with the rest of your system. Here's how to do it using
  the `homebrew`_ package manager:

  * Install `homebrew`_ following the instructions in https://brew.sh/

  * Update your ``PATH`` variable to state that homebrew packages should be
    used before system packages (Change ``.bashrc`` to ``.zshrc`` accordingly
    if you're using `zsh`_ as default shell)::

      echo "export PATH=/usr/local/bin:/usr/local/sbin:$PATH" >> ~/.bashrc

  * Reload ``.bashrc`` to ensure the changes have taken place::

      source ~/.bashrc

  * Install python::

      brew install python

  * Latest versions of python have ``pip`` bundled with them so you won't need
    to install it separately. If this is not the case, upgrade python::

      brew update; brew upgrade python

*   *(Optional)* :ref:`Install Scrapy inside a Python virtual environment
    <intro-using-virtualenv>`.

  This method is a workaround for the above macOS issue, but it's an overall
  good practice for managing dependencies and can complement the first method.

After any of these workarounds you should be able to install Scrapy::

  pip install Scrapy


PyPy
----

We recommend using the latest PyPy version.
For PyPy3, only Linux installation was tested.

Most Scrapy dependencies now have binary wheels for CPython, but not for PyPy.
This means that these dependencies will be built during installation.
On macOS, you are likely to face an issue with building the Cryptography
dependency. The solution to this problem is described
`here <https://github.com/pyca/cryptography/issues/2692#issuecomment-272773481>`_,
that is to ``brew install openssl`` and then export the flags that this command
recommends (only needed when installing Scrapy). Installing on Linux has no special
issues besides installing build dependencies.
Installing Scrapy with PyPy on Windows is not tested.

You can check that Scrapy is installed correctly by running ``scrapy bench``.
If this command gives errors such as
``TypeError: ... got 2 unexpected keyword arguments``, this means
that setuptools was unable to pick up one PyPy-specific dependency.
To fix this issue, run ``pip install 'PyPyDispatcher>=2.1.0'``.


.. _intro-install-troubleshooting:

Troubleshooting
===============

AttributeError: 'module' object has no attribute 'OP_NO_TLSv1_1'
----------------------------------------------------------------

After you install or upgrade Scrapy, Twisted or pyOpenSSL, you may get an
exception with the following traceback::

    […]
      File "[…]/site-packages/twisted/protocols/tls.py", line 63, in <module>
        from twisted.internet._sslverify import _setAcceptableProtocols
      File "[…]/site-packages/twisted/internet/_sslverify.py", line 38, in <module>
        TLSVersion.TLSv1_1: SSL.OP_NO_TLSv1_1,
    AttributeError: 'module' object has no attribute 'OP_NO_TLSv1_1'

The reason you get this exception is that your system or virtual environment
has a version of pyOpenSSL that your version of Twisted does not support.

To install a version of pyOpenSSL that your version of Twisted supports,
reinstall Twisted with the :code:`tls` extra option::

    pip install twisted[tls]

For details, see `Issue #2473 <https://github.com/scrapy/scrapy/issues/2473>`_.

.. _Python: https://www.python.org/
.. _pip: https://pip.pypa.io/en/latest/installing/
.. _lxml: https://lxml.de/index.html
.. _parsel: https://pypi.org/project/parsel/
.. _w3lib: https://pypi.org/project/w3lib/
.. _twisted: https://twistedmatrix.com/trac/
.. _cryptography: https://cryptography.io/en/latest/
.. _pyOpenSSL: https://pypi.org/project/pyOpenSSL/
.. _setuptools: https://pypi.python.org/pypi/setuptools
.. _homebrew: https://brew.sh/
.. _zsh: https://www.zsh.org/
.. _Anaconda: https://docs.anaconda.com/anaconda/
.. _Miniconda: https://docs.conda.io/projects/conda/en/latest/user-guide/install/index.html
.. _Visual Studio: https://docs.microsoft.com/en-us/visualstudio/install/install-visual-studio
.. _Microsoft C++ Build Tools: https://visualstudio.microsoft.com/visual-cpp-build-tools/
.. _conda-forge: https://conda-forge.org/
