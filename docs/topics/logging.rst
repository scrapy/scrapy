.. _topics-logging:

=======
Logging
=======

Scrapy provides a logging facility which can be used through the
:mod:`scrapy.log` module. The current underling implementation uses `Twisted
logging`_ but this may change in the future.

.. _Twisted logging: http://twistedmatrix.com/projects/core/documentation/howto/logging.html

Logging service must be explicitly started through the :func:`scrapy.log.start` function.

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
using the :setting:`LOGLEVEL` setting.

How to log messages
===================

Here's a quick example of how to log a message using the ``WARNING`` level::

    from scrapy import log
    log.msg("This is a warning", level=log.WARNING)

Logging from Spiders
====================

The recommended way to log from spiders is by using the Spider
:meth:`~scrapy.spider.BaseSpider.log` method, which already populates the
``domain`` argument of the :func:`scrapy.log.msg` function. The other arguments
are passed directly to the :func:`~scrapy.log.msg` function.

scrapy.log module
=================

.. module:: scrapy.log
   :synopsis: Logging facility

.. attribute:: log_level

   The current log level being used

.. attribute:: started

   A boolean which is ``True`` is logging has been started or ``False`` otherwise.

.. function:: start(logfile=None, loglevel=None, log_stdout=None)

    Start the logging facility. This must be called before actually logging any
    messages. Otherwise, messages logged before this call will get lost.

    ``logfile`` is a string with the file path to use for logging output. If
    omitted, :setting:`LOGFILE` setting will be used. If both are ``None``, log
    will be sent to standard output (if ``log_stdout`` or :setting:`LOG_STDOUT` is
    ``True``) or standard error (if ``log_stderr`` or :setting:`LOG_STDOUT` is
    ``False``).

    ``loglevel`` is the logging level. Availables ones are: :data:`CRITICAL`,
    :data:`ERROR`, :data:`WARNING`, :data:`INFO` and :data:`DEBUG`.

    ``log_stdout`` is a boolean which specifies if log should be sent to standard
    output (if ``True``) or standard error (if ``False``)

.. function:: msg(message, level=INFO, component=BOT_NAME, domain=None)

    Log a message

    :param message: the message to log
    :type message: str

    :param level: the log level for this message. See
        :ref:`topics-logging-levels`.

    :param component: the component to use for logging, it defaults to
        :setting:`BOT_NAME`
    :type component: str

    :param domain: the spider domain to use for logging this message. This
        parameter should always be used when logging things related to a
        particular spider.
    :type domain: str

.. function:: exc(message, level=ERROR, component=BOT_NAME, domain=None)

    Log an exception. Similar to ``msg()`` but it also appends a stack trace
    report using `traceback.format_exc`.

    .. _traceback.format_exc: http://docs.python.org/library/traceback.html#traceback.format_exc

    It accepts the same parameters as the :func:`msg` function.

.. data:: CRITICAL

    Log level for critical errors

.. data:: ERROR

    Log level for errors

.. data:: WARNING

    Log level for warnings

.. data:: INFO

    Log level for informational messages (recommended level for production)

.. data:: DEBUG

    Log level for debugging messages (recommended level for development)

