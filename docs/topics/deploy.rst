.. _topics-deploy:

=================
Deploying Spiders
=================

This section describes the different options you have for deploying your Scrapy
spiders to run them on a regular basis. Running Scrapy spiders in your local
machine is very convenient for the (early) development stage, but not so much
when you need to execute long-running spiders or move spiders to run in
production continuously. This is where the solutions for deploying Scrapy
spiders come in.

Popular choices for deploying Scrapy spiders are:

* :ref:`Scrapyd <deploy-scrapyd>` (open source)
* :ref:`Zyte Scrapy Cloud <deploy-scrapy-cloud>` (cloud-based)

.. _deploy-scrapyd:

Deploying to a Scrapyd Server
=============================

`Scrapyd`_ is an open source application to run Scrapy spiders. It provides
a server with HTTP API, capable of running and monitoring Scrapy spiders.

To deploy spiders to Scrapyd, you can use the scrapyd-deploy tool provided by
the `scrapyd-client`_ package. Please refer to the `scrapyd-deploy
documentation`_ for more information.

Scrapyd is maintained by some of the Scrapy developers.

.. _deploy-scrapy-cloud:

Deploying to Zyte Scrapy Cloud
==============================

`Zyte Scrapy Cloud`_ is a hosted, cloud-based service by Zyte_, the company
behind Scrapy.

Zyte Scrapy Cloud removes the need to setup and monitor servers and provides a
nice UI to manage spiders and review scraped items, logs and stats.

To deploy spiders to Zyte Scrapy Cloud you can use the `shub`_ command line
tool.
Please refer to the `Zyte Scrapy Cloud documentation`_ for more information.

Zyte Scrapy Cloud is compatible with Scrapyd and one can switch between
them as needed - the configuration is read from the ``scrapy.cfg`` file
just like ``scrapyd-deploy``.

.. _Deploying your project: https://scrapyd.readthedocs.io/en/latest/deploy.html
.. _Scrapyd: https://github.com/scrapy/scrapyd
.. _scrapyd-client: https://github.com/scrapy/scrapyd-client
.. _scrapyd-deploy documentation: https://scrapyd.readthedocs.io/en/latest/deploy.html
.. _shub: https://shub.readthedocs.io/en/latest/
.. _Zyte: https://www.zyte.com/
.. _Zyte Scrapy Cloud: https://www.zyte.com/scrapy-cloud/
.. _Zyte Scrapy Cloud documentation: https://docs.zyte.com/scrapy-cloud.html
