.. _topics-deployment:

==========
Deployment
==========

The recommended way to deploy Scrapy projects to a server is through `Scrapyd`_.

.. _Scrapyd: https://github.com/scrapy/scrapyd

Deploying to a Scrapyd Server
=============================

You can deploy to a Scrapyd server using the `Scrapyd client <https://github.com/scrapy/scrapyd-client>`_. You can add targets to your ``scrapy.cfg`` file which can be deployed to using the ``scrapyd-deploy`` command.

The basic syntax is as follows:

    scrapyd-deploy <target> -p <project>

For more information please refer to the `Deploying your project`_ section.

.. _Deploying your project: https://scrapyd.readthedocs.org/en/latest/deploy.html

Deploying to Scrapinghub
========================

You can deploy to Scrapinghub using Scrapinghub's command line client, `shub`_. The configuration is read from the ``scrapy.cfg`` file just like ``scrapyd-deploy``.

.. _shub: https://github.com/scrapinghub/shub
