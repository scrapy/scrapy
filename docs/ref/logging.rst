.. _ref-logging:

=======
Logging
=======

Scrapy logging facility is provided by the ``scrapy.log`` module, and is
currently implemented as a wrapper for `Twisted logging`_.

.. _Twisted logging: http://twistedmatrix.com/projects/core/documentation/howto/logging.html

Logging must be started through the ``scrapy.log.start`` function.

Quick example
=============

Here's a quick example of how to log a message using the ``WARNING`` level::

    from scrapy import log
    log.msg("This is a warning", level=log.WARNING)

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

    ``loglevel`` is the logging level. Availables ones are:
        * ``scrapy.log.CRITICAL``
        * ``scrapy.log.ERROR``
        * ``scrapy.log.WARNING``
        * ``scrapy.log.INFO``
        * ``scrapy.log.DEBUG``

    ``log_stdout`` is a boolean which specifies if log should be sent to standard
    output (if ``True``) or standard error (if ``False``)

.. function:: msg(message, level=INFO, component=BOT_NAME, domain=None)

    Log a message

    ``message`` is a string with the message to log

    ``level`` is the log level for this message. See ``start()`` function for
    available log levels.

    ``component`` is a string with the component to use for logging, it defaults to :setting:`BOT_NAME`

    ``domain`` is a string with the domain to use for logging this message.
    This parameter should always be used when logging stuff paricular to any
    domain or spider.

.. function:: exc(message, level=ERROR, component=BOT_NAME, domain=None)

    Log an exception. Similar to ``msg()`` but it also appends a stack trace
    report using `traceback.format_exc`.

    .. _traceback.format_exc: http://docs.python.org/library/traceback.html#traceback.format_exc

    ``message`` - same as ``msg()`` function
    
    ``level`` - same as ``msg()`` function

    ``component`` - same as ``msg()`` function

    ``domain`` - same as ``msg()`` function

Logging from Spiders
====================

The recommended way for logging from spiders is to use the Spider ``log()``
method, which already populates the :func:`~scrapy.log.msg` ``domain``
argument. The other arguments of the Spider ``log()`` method are the same as
the :func:`~scrapy.log.msg` function.

