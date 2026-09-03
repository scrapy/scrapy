.. _intro-install:

==================
Installation guide
==================

.. _faq-python-versions:

Supported Python versions
=========================

Scrapy requires Python 3.10+, either the CPython implementation (default) or
the PyPy implementation (see :ref:`python:implementations`).

.. _intro-install-scrapy:

Installing Scrapy
=================

Install Scrapy and its dependencies from PyPI with::

    pip install scrapy

We strongly recommend that you install Scrapy in :ref:`a dedicated virtual
environment <intro-using-virtualenv>`, to avoid conflicting with your system
packages.

Alternatively:

-   From a `uv`_ project, e.g. one created with ``uv init``. ``uv`` manages the
    virtual environment for you::

        uv add scrapy

-   From the `conda-forge`_ channel, with ``conda``::

        conda install -c conda-forge scrapy

If the installation fails while building one of the dependencies, see
:ref:`install-no-wheel`.


Things that are good to know
----------------------------

Scrapy is written in pure Python and depends on a few key Python packages (among others):

* `lxml`_, an efficient XML and HTML parser
* `parsel`_, an HTML/XML data extraction library written on top of lxml,
* `w3lib`_, a multi-purpose helper for dealing with URLs and web page encodings
* `twisted`_, an asynchronous networking framework
* `cryptography`_ and `pyOpenSSL`_, to deal with various network-level security needs

Some of these packages include compiled code. They provide binary wheels for
common platforms, so that installing them requires no compiler; see
:ref:`install-no-wheel` if no wheel matches your platform.


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

.. _extras:

Optional extras
===============

Scrapy provides optional :ref:`extras <pypug:dependency-specifiers-extras>`
that install additional dependencies to enable specific features. To install
Scrapy with one or more extras, list them in square brackets:

.. code-block:: console

    pip install scrapy[s3,images]

The following extras are available:

.. list-table::
   :header-rows: 1

   * - Extra
     - Provides
   * - ``bpython``
     - :ref:`bpython shell <shell-config>`
   * - ``gcs``
     - :ref:`Google Cloud Storage <topics-feed-storage-gcs>` for
       :ref:`feed exports <topics-feed-exports>` and
       :ref:`media pipelines <media-pipeline-gcs>`
   * - ``httpx``
     - :ref:`httpx-handler`, including its HTTP/2 and SOCKS proxy support
   * - ``images``
     - :ref:`Images pipeline <images-pipeline>`
   * - ``ipython``
     - :ref:`IPython shell <shell-config>`
   * - ``ptpython``
     - :ref:`ptpython shell <shell-config>`
   * - ``robotparser``
     - :ref:`Robotexclusionrulesparser robots.txt parsing <rerp-parser>`
   * - ``s3``
     - :ref:`Amazon S3 <topics-feed-storage-s3>` storage for
       :ref:`feed exports <topics-feed-exports>`,
       :ref:`media pipelines <media-pipelines-s3>`, and
       :ref:`S3 downloads <s3-handler>`
   * - ``twisted-http2``
     - :ref:`twisted-http2-handler`
   * - ``uvloop``
     - `uvloop <https://github.com/MagicStack/uvloop>`_ event loop


.. _install-notes:
.. _intro-install-platform-notes:

Platform specific installation notes
====================================

.. _install-windows:
.. _intro-install-windows:

Windows
-------

Install Scrapy :ref:`as described above <intro-install-scrapy>`. Dependencies
that include compiled code provide wheels for 64-bit x86 Windows, so no
compiler is needed.

On 32-bit or ARM64 Windows some of those wheels are missing, see
:ref:`install-no-wheel`. An additional option there is `WSL`_, which lets you
follow the :ref:`Linux instructions <install-linux>` instead. Note that your
code then runs on Linux, so Windows paths do not work in settings like
:setting:`FEEDS`.

.. _install-linux:
.. _intro-install-ubuntu:

Linux
-----

Install Scrapy :ref:`as described above <intro-install-scrapy>`. Dependencies
that include compiled code provide ``manylinux`` and ``musllinux`` wheels, so
no compiler is needed.

**Don't** use the Scrapy package provided by your distribution, e.g.
``python-scrapy`` on Debian and Ubuntu, they are typically too old and slow to
catch up with the latest Scrapy release.

.. _install-macos:
.. _intro-install-macos:

macOS
-----

Install Scrapy :ref:`as described above <intro-install-scrapy>`. Dependencies
that include compiled code provide wheels for both Intel and Apple silicon, so
no compiler is needed.

We recommend against using the Python interpreter that comes with macOS.
Install a separate one instead, e.g. with `homebrew`_::

    brew install python


PyPy
----

We recommend using the latest PyPy version.

Dependencies that include compiled code provide PyPy wheels for Linux and
64-bit x86 Windows. On macOS some are missing, see :ref:`install-no-wheel`.

You can check that Scrapy is installed correctly by running ``scrapy bench``.
If this command gives errors such as
``TypeError: ... got 2 unexpected keyword arguments``, this means
that the ``PyPyDispatcher`` dependency wasn't installed. To fix this issue, run
``pip install 'PyPyDispatcher>=2.1.0'``.


.. _install-troubleshooting:
.. _intro-install-troubleshooting:

Troubleshooting
===============

.. _install-no-wheel:

Installation fails while building a dependency
----------------------------------------------

When ``pip`` finds no wheel matching your Python version and platform, it
builds the dependency from its source distribution instead, which requires a
build toolchain and the libraries that the dependency wraps. To check whether
that is what fails for you, ask ``pip`` for wheels only::

    pip install --only-binary :all: scrapy

With ``uv``, use ``uv add --no-build scrapy`` instead.

If that fails, no wheel is available, and you have the following options,
easiest first:

-   Use an older Python version. Wheels for a new Python version may take
    weeks to become available after its release.

-   Use ``conda``, e.g. through `Miniforge`_, and install Scrapy from the
    `conda-forge`_ channel.

-   Build the dependency from source, following its own installation
    instructions, e.g. `lxml installation`_ or :doc:`cryptography installation
    <cryptography:installation>`. Beyond a C compiler, this may require a Rust
    compiler, development files of libraries like libxml2 or OpenSSL, or both.

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

.. _lxml: https://lxml.de/index.html
.. _lxml installation: https://lxml.de/installation.html
.. _parsel: https://pypi.org/project/parsel/
.. _w3lib: https://pypi.org/project/w3lib/
.. _twisted: https://twisted.org/
.. _cryptography: https://cryptography.io/en/latest/
.. _pyOpenSSL: https://pypi.org/project/pyOpenSSL/
.. _homebrew: https://brew.sh/
.. _uv: https://docs.astral.sh/uv/
.. _Miniforge: https://conda-forge.org/download/
.. _conda-forge: https://conda-forge.org/
.. _WSL: https://learn.microsoft.com/en-us/windows/wsl/install
