.. _topics-ubuntu:

===============
Ubuntu packages
===============

.. versionadded:: 0.10

`Insophia`_ publishes apt-gettable packages which are generally fresher than
those in Ubuntu, and more stable too since they're continuously built from
`Github repo`_ (master & stable branches) and so they contain the latest bug
fixes.

To use the packages, just add the following line to your
``/etc/apt/sources.list``, and then run ``aptitude update`` and ``aptitude
install scrapy-0.13``::

    deb http://archive.scrapy.org/ubuntu DISTRO main

Replacing ``DISTRO`` with the name of your Ubuntu release, which you can get
with command::

    lsb_release -cs

Supported Ubuntu releases are: ``karmic``, ``lucid``, ``maverick``, ``natty``,
``oneiric``.

For Ubuntu Oneiric (11.10)::

    deb http://archive.scrapy.org/ubuntu oneiric main

For Ubuntu Natty (11.04)::

    deb http://archive.scrapy.org/ubuntu natty main

For Ubuntu Maverick (10.10)::

    deb http://archive.scrapy.org/ubuntu maverick main

For Ubuntu Lucid (10.04)::

    deb http://archive.scrapy.org/ubuntu lucid main

For Ubuntu Karmic (9.10)::

    deb http://archive.scrapy.org/ubuntu karmic main

.. warning:: Please note that these packages are updated frequently, and so if
   you find you can't download the packages, try updating your apt package
   lists first, e.g., with ``apt-get update`` or ``aptitude update``.

The public GPG key used to sign these packages can be imported into you APT
keyring as follows::

    curl -s http://archive.scrapy.org/ubuntu/archive.key | sudo apt-key add -

.. _Insophia: http://insophia.com/
.. _Github repo: https://github.com/scrapy/scrapy
