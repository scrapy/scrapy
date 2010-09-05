.. _topics-ubuntu:

===============
Ubuntu packages
===============

.. versionadded:: 0.10

`Insophia`_ publishes apt-gettable packages which are generally fresher than
those in Ubuntu, and more stable too since they're built periodically from
`Scrapy Mercurial repositories`_ (stable & development) and so they contain the
latest bug fixes.

To use the packages, add a line to your ``/etc/apt/sources.list``, then run
``aptitude update`` and ``aptitude install scrapy``.

.. warning:: Please note that these packages are updated frequently, and so if
   you find you can't download the packages, try updating your apt package
   lists first, e.g., with ``apt-get update`` or ``aptitude update``.

For Ubuntu Lucid (10.04) and Ubuntu Karmic (9.10)::

    deb http://archive.scrapy.org/ubuntu 0.10 main

The public GPG key used to sign these packages can be imported into you APT
keyring as follows::

    curl -s http://archive.scrapy.org/ubuntu/archive.key | sudo apt-key add -

.. _Insophia: http://insophia.com/
.. _Scrapy Mercurial repositories: http://hg.scrapy.org/
