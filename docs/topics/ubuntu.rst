.. _topics-ubuntu:

===============
Ubuntu packages
===============

.. versionadded:: 0.10

`Scrapinghub`_ publishes debian packages, separated in three different
distributions: `main` (stable) / `testing` / `unstable`. The
most updated version will be always in the `unstable` distribution.

The process is:
 * Take the latest version from `unstable` weeky, copy it to `testing`.
 * Run real world tests for some days.
 * If the tests are successful, promote the package from `testing` to `main`.

To use the packages:

1. Import the GPG key used to sign Scrapy packages into APT keyring::

    sudo apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv 627220E7

2. Create `/etc/apt/sources.list.d/scrapy.list` file using the following command::

    echo 'deb http://archive.scrapy.org/ubuntu scrapy main' | sudo tee /etc/apt/sources.list.d/scrapy.list

.. note:: Replace `main` with `unstable` if you want to be on the bleeding edge.

3. Update package lists and install the scrapy package:

   .. parsed-literal::

      sudo apt-get update && sudo apt-get install scrapy

.. note:: Repeat step 3 if you are trying to upgrade Scrapy.

.. warning:: `python-scrapy` is a different package provided by official debian
   repositories, it's very outdated and it isn't supported by Scrapy team.

.. _Scrapinghub: http://scrapinghub.com/
.. _Github repo: https://github.com/scrapy/scrapy
