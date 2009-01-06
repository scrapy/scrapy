.. _topics-robotstxt:

==========
robots.txt
==========

Scrapy deals with robots.txt files using a :ref:`topics-downloader-middleware`.
called `RobotsTxtMiddleware`.

To make sure Scrapy respects robots.txt files make sure the following
middleware is enabled::

     scrapy.contrib.downloadermiddleware.robotstxt.RobotsTxtMiddleware

And the :setting:`ROBOTSTXT_OBEY` setting is enabled.

Keep in mind that, if you crawl using multiple concurrent requests per domain,
Scrapy could get to download some forbidden pages if they were requested to
download before the robots.txt file was downloaded. This is a known limitation
of the current robots.txt middleware and will be fixed in the future.
