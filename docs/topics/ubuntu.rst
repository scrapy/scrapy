:orphan: Ubuntu packages are obsolete

.. _topics-ubuntu:

===============
Ubuntu packages
===============

.. versionadded:: 0.10

`Scrapinghub`_ publishes apt-gettable packages which are generally fresher than
those in Ubuntu, and more stable too since they're continuously built from
`GitHub repo`_ (master & stable branches) and so they contain the latest bug
fixes.

.. caution:: These packages are currently not updated and may not work on
   Ubuntu 16.04 and above, see :issue:`2076` and :issue:`2137`.

To use the packages:

1. Import the GPG key used to sign Scrapy packages into APT keyring::

    sudo apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv 627220E7

2. Create `/etc/apt/sources.list.d/scrapy.list` file using the following command::

    echo 'deb http://archive.scrapy.org/ubuntu scrapy main' | sudo tee /etc/apt/sources.list.d/scrapy.list

3. Update package lists and install the scrapy package:

   .. parsed-literal::

      sudo apt-get update && sudo apt-get install scrapy

.. note:: Repeat step 3 if you are trying to upgrade Scrapy.

.. warning:: `python-scrapy` is a different package provided by official debian
   repositories, it's very outdated and it isn't supported by Scrapy team.

.. _Scrapinghub: http://scrapinghub.com/
.. _GitHub repo: https://github.com/scrapy/scrapy
