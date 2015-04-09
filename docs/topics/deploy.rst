.. _topics-deploy:

=================
Deploying Spiders
=================

This section describes the different options you have for deploying your Scrapy
spiders to run them on a regular basis. Running Scrapy spiders in your local
machine is very convenient for the (early) development stage, but not so much
when you need to execute long-running spiders or move spiders to run in
production continously. This is where the solutions for deploying Scrapy
spiders come in.

The most popular choices, for deploying Scrapy spiders, are:

* :ref:`Scrapy Cloud <deploy-scrapy-cloud>` (open source, easier to setup)
* :ref:`Scrapyd <deploy-scrapyd>` (open source, harder to setup)

.. _deploy-scrapy-cloud:

Deploying to Scrapy Cloud
=========================

`Scrapy Cloud`_ is a hosted, cloud-based service by `Scrapinghub`_, the company
behind Scrapy.

Advantages:

- easy to setup (no need to setup or manage servers)
- well-designed UI to manage spiders and review scraped items, logs and stats
- cheap pricing (cheaper than renting a server, for small workloads)

Disadvantages:

- it's not open source

To deploy spiders to Scrapy Cloud you can use the `shub`_ command line tool.
Please refer to the `Scrapy Cloud documentation`_ for more information.

The configuration is read from the ``scrapy.cfg`` file just like
``scrapyd-deploy``.

.. _deploy-scrapyd:

Deploying to a Scrapyd Server
=============================

`Scrapyd`_ is an open source application to run Scrapy spiders. It is
maintained by some of the Scrapy developers.

Advantages:

- it's open source, so it can be installed and run anywhere

Disadvantages:

- simple UI (no analytics, graphs or rich log/items browsing)
- requires setting up servers, installing and configuring scrapyd on them. An
  APT repo with Ubuntu packages is provided by the Scrapyd team

To deploy spiders to Scrapyd, you can use the scrapyd-deploy tool provided by
the `scrapyd-client`_ package. Please refer to the `scrapyd-deploy
documentation`_ for more information.

.. _Scrapyd: https://github.com/scrapy/scrapyd
.. _Deploying your project: https://scrapyd.readthedocs.org/en/latest/deploy.html
.. _Scrapy Cloud: http://scrapinghub.com/scrapy-cloud/
.. _scrapyd-client: https://github.com/scrapy/scrapyd-client
.. _shub: http://doc.scrapinghub.com/shub.html
.. _scrapyd-deploy documentation: http://scrapyd.readthedocs.org/en/latest/deploy.html
.. _Scrapy Cloud documentation: http://doc.scrapinghub.com/scrapy-cloud.html
.. _Scrapinghub: http://scrapinghub.com/
