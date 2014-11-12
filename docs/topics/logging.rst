.. _topics-logging:

=======
Logging
=======

Scrapy provides a logging facility which can be used through the
:mod:`scrapy.log` module. The current underlying implementation uses `Twisted
logging`_ but this may change in the future.

.. _Twisted logging: http://twistedmatrix.com/projects/core/documentation/howto/logging.html

The logging service must be explicitly started through the
:func:`scrapy.log.start` function to catch the top level Scrapy's log messages.
On top of that, each crawler has its own independent log observer
(automatically attached when it's created) that intercepts its spider's log
messages.

.. _topics-logging-levels:

Log levels
==========

Scrapy provides 5 logging levels:

1. :data:`~scrapy.log.CRITICAL` - for critical errors
2. :data:`~scrapy.log.ERROR` - for regular errors
3. :data:`~scrapy.log.WARNING` - for warning messages
4. :data:`~scrapy.log.INFO` - for informational messages
5. :data:`~scrapy.log.DEBUG` - for debugging messages

How to set the log level
========================

You can set the log level using the `--loglevel/-L` command line option, or
using the :setting:`LOG_LEVEL` setting.

How to log messages
===================

Here's a quick example of how to log a message using the ``WARNING`` level::

    from scrapy import log
    log.msg("This is a warning", level=log.WARNING)

Logging from Spiders
====================

The recommended way to log from spiders is by using the Spider
:meth:`~scrapy.spider.Spider.log` method, which already populates the
``spider`` argument of the :func:`scrapy.log.msg` function. The other arguments
are passed directly to the :func:`~scrapy.log.msg` function.

scrapy.log module
=================

.. module:: scrapy.log
   :synopsis: Logging facility

.. function:: start(logfile=None, loglevel=None, logstdout=None)

    Start the top level Scrapy logger. This must be called before actually
    logging any top level messages (those logged using this module's
    :func:`~scrapy.log.msg` function instead of the :meth:`Spider.log
    <scrapy.spider.Spider.log>` method). Otherwise, messages logged before this
    call will get lost.

    :param logfile: the file path to use for logging output. If omitted, the
        :setting:`LOG_FILE` setting will be used. If both are ``None``, the log
        will be sent to standard error.
    :type logfile: str

    :param loglevel: the minimum logging level to log. Available values are:
        :data:`CRITICAL`, :data:`ERROR`, :data:`WARNING`, :data:`INFO` and
        :data:`DEBUG`.

    :param logstdout: if ``True``, all standard output (and error) of your
        application will be logged instead. For example if you "print 'hello'"
        it will appear in the Scrapy log. If omitted, the :setting:`LOG_STDOUT`
        setting will be used.
    :type logstdout: boolean

.. function:: msg(message, level=INFO, spider=None)

    Log a message

    :param message: the message to log
    :type message: str

    :param level: the log level for this message. See
        :ref:`topics-logging-levels`.

    :param spider: the spider to use for logging this message. This parameter
        should always be used when logging things related to a particular
        spider.
    :type spider: :class:`~scrapy.spider.Spider` object

.. data:: CRITICAL

    Log level for critical errors

.. data:: ERROR

    Log level for errors

.. data:: WARNING

    Log level for warnings

.. data:: INFO

    Log level for informational messages (recommended level for production
    deployments)

.. data:: DEBUG

    Log level for debugging messages (recommended level for development)

Logging settings
================

These settings can be used to configure the logging:

* :setting:`LOG_ENABLED`
* :setting:`LOG_ENCODING`
* :setting:`LOG_FILE`
* :setting:`LOG_LEVEL`
* :setting:`LOG_STDOUT`

