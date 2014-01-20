.. _topics-ubuntu:

===============
Ubuntu packages
===============

.. versionadded:: 0.10

`Scrapinghub`_ publishes apt-gettable packages which are generally fresher than
those in Ubuntu, and more stable too since they're continuously built from
`Github repo`_ (master & stable branches) and so they contain the latest bug
fixes.

To use the packages, just add the following line to your
``/etc/apt/sources.list``, and then run ``aptitude update`` and
``apt-get install scrapy-0.22``::

    deb http://archive.scrapy.org/ubuntu DISTRO main

Replacing ``DISTRO`` with the name of your Ubuntu release, which you can get
with command::

    lsb_release -cs

Supported Ubuntu releases are: ``precise``, ``quantal``, ``raring``.

For Ubuntu Raring (13.04)::

    deb http://archive.scrapy.org/ubuntu raring main

For Ubuntu Quantal (12.10)::

    deb http://archive.scrapy.org/ubuntu quantal main

For Ubuntu Precise (12.04)::

    deb http://archive.scrapy.org/ubuntu precise main

.. warning:: Please note that these packages are updated frequently, and so if
   you find you can't download the packages, try updating your apt package
   lists first, e.g., with ``apt-get update`` or ``aptitude update``.

The public GPG key used to sign these packages can be imported into you APT
keyring as follows::

    curl -s http://archive.scrapy.org/ubuntu/archive.key | sudo apt-key add -

.. _Scrapinghub: http://scrapinghub.com/
.. _Github repo: https://github.com/scrapy/scrapy
