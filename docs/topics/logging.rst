.. _topics-logging:

=======
Logging
=======

.. note::
    :mod:`scrapy.log` has been deprecated alongside its functions in favor of
    explicit calls to the Python standard logging. Keep reading to learn more
    about the new logging system.

Scrapy uses `Python's builtin logging system
<https://docs.python.org/3/library/logging.html>`_ for event logging. We'll
provide some simple examples to get you started, but for more advanced
use-cases it's strongly suggested to read thoroughly its documentation.

Logging works out of the box, and can be configured to some extent with the
Scrapy settings listed in :ref:`topics-logging-settings`.

Scrapy calls :func:`scrapy.utils.log.configure_logging` to set some reasonable
defaults and handle those settings in :ref:`topics-logging-settings` when
running commands, so it's recommended to manually call it if you're running
Scrapy from scripts as described in :ref:`run-from-script`.

.. _topics-logging-levels:

Log levels
==========

Python's builtin logging defines 5 different levels to indicate severity on a
given log message. Here are the standard ones, listed in decreasing order:

1. ``logging.CRITICAL`` - for critical errors (highest severity)
2. ``logging.ERROR`` - for regular errors
3. ``logging.WARNING`` - for warning messages
4. ``logging.INFO`` - for informational messages
5. ``logging.DEBUG`` - for debugging messages (lowest severity)

How to log messages
===================

Here's a quick example of how to log a message using the ``logging.WARNING``
level::

    import logging
    logging.warning("This is a warning")

There are shortcuts for issuing log messages on any of the standard 5 levels,
and there's also a general ``logging.log`` method which takes a given level as
argument.  If you need so, last example could be rewrote as::

    import logging
    logging.log(logging.WARNING, "This is a warning")

On top of that, you can create different "loggers" to encapsulate messages (For
example, a common practice it's to create different loggers for every module).
These loggers can be configured independently, and they allow hierarchical
constructions.

Last examples use the root logger behind the scenes, which is a top level
logger where all messages are propagated to (unless otherwise specified). Using
``logging`` helpers is merely a shortcut for getting the root logger
explicitly, so this is also an equivalent of last snippets::

    import logging
    logger = logging.getLogger()
    logger.warning("This is a warning")

You can use a different logger just by getting its name with the
``logging.getLogger`` function::

    import logging
    logger = logging.getLogger('mycustomlogger')
    logger.warning("This is a warning")

Finally, you can ensure having a custom logger for any module you're working on
by using the ``__name__`` variable, which is populated with current module's
path::

    import logging
    logger = logging.getLogger(__name__)
    logger.warning("This is a warning")

.. seealso::

    Module logging, `HowTo <https://docs.python.org/2/howto/logging.html>`_
        Basic Logging Tutorial

    Module logging, `Loggers <https://docs.python.org/2/library/logging.html#logger-objects>`_
        Further documentation on loggers

.. _topics-logging-from-spiders:

Logging from Spiders
====================

Scrapy provides a :data:`~scrapy.spiders.Spider.logger` within each Spider
instance, that can be accessed and used like this::

    import scrapy

    class MySpider(scrapy.Spider):

        name = 'myspider'
        start_urls = ['http://scrapinghub.com']

        def parse(self, response):
            self.logger.info('Parse function called on %s', response.url)

That logger is created using the Spider's name, but you can use any custom
Python logger you want. For example::

    import logging
    import scrapy

    logger = logging.getLogger('mycustomlogger')

    class MySpider(scrapy.Spider):

        name = 'myspider'
        start_urls = ['http://scrapinghub.com']

        def parse(self, response):
            logger.info('Parse function called on %s', response.url)

.. _topics-logging-configuration:

Logging configuration
=====================

Loggers on their own don't manage how messages sent through them are displayed.
For this task, different "handlers" can be attached to any logger instance and
they will redirect those messages to appropriate destinations, such as the
standard output, files, emails, etc.

By default, Scrapy sets and configures a handler for the root logger, based on
the settings below.

.. _topics-logging-settings:

Logging settings
----------------

These settings can be used to configure the logging:

* :setting:`LOG_FILE`
* :setting:`LOG_ENABLED`
* :setting:`LOG_ENCODING`
* :setting:`LOG_LEVEL`
* :setting:`LOG_FORMAT`
* :setting:`LOG_DATEFORMAT`
* :setting:`LOG_STDOUT`
* :setting:`LOG_SHORT_NAMES`

The first couple of settings define a destination for log messages. If
:setting:`LOG_FILE` is set, messages sent through the root logger will be
redirected to a file named :setting:`LOG_FILE` with encoding
:setting:`LOG_ENCODING`. If unset and :setting:`LOG_ENABLED` is ``True``, log
messages will be displayed on the standard error. Lastly, if
:setting:`LOG_ENABLED` is ``False``, there won't be any visible log output.

:setting:`LOG_LEVEL` determines the minimum level of severity to display, those
messages with lower severity will be filtered out. It ranges through the
possible levels listed in :ref:`topics-logging-levels`.

:setting:`LOG_FORMAT` and :setting:`LOG_DATEFORMAT` specify formatting strings
used as layouts for all messages. Those strings can contain any placeholders
listed in `logging's logrecord attributes docs
<https://docs.python.org/2/library/logging.html#logrecord-attributes>`_ and
`datetime's strftime and strptime directives
<https://docs.python.org/2/library/datetime.html#strftime-and-strptime-behavior>`_
respectively.

If :setting:`LOG_SHORT_NAMES` is set, then the logs will not display the scrapy
component that prints the log. It is unset by default, hence logs contain the 
scrapy component responsible for that log output.

Command-line options
--------------------

There are command-line arguments, available for all commands, that you can use
to override some of the Scrapy settings regarding logging.

* ``--logfile FILE``
    Overrides :setting:`LOG_FILE`
* ``--loglevel/-L LEVEL``
    Overrides :setting:`LOG_LEVEL`
* ``--nolog``
    Sets :setting:`LOG_ENABLED` to ``False``

.. seealso::

    Module `logging.handlers <https://docs.python.org/2/library/logging.handlers.html>`_
        Further documentation on available handlers

Advanced customization
----------------------

Because Scrapy uses stdlib logging module, you can customize logging using
all features of stdlib logging.

For example, let's say you're scraping a website which returns many
HTTP 404 and 500 responses, and you want to hide all messages like this::

    2016-12-16 22:00:06 [scrapy.spidermiddlewares.httperror] INFO: Ignoring
    response <500 http://quotes.toscrape.com/page/1-34/>: HTTP status code
    is not handled or not allowed

The first thing to note is a logger name - it is in brackets:
``[scrapy.spidermiddlewares.httperror]``. If you get just ``[scrapy]`` then
:setting:`LOG_SHORT_NAMES` is likely set to True; set it to False and re-run
the crawl.

Next, we can see that the message has INFO level. To hide it
we should set logging level for ``scrapy.spidermiddlewares.httperror``
higher than INFO; next level after INFO is WARNING. It could be done
e.g. in the spider's ``__init__`` method::

    import logging
    import scrapy


    class MySpider(scrapy.Spider):
        # ...
        def __init__(self, *args, **kwargs):
            logger = logging.getLogger('scrapy.spidermiddlewares.httperror')
            logger.setLevel(logging.WARNING)
            super().__init__(*args, **kwargs)

If you run this spider again then INFO messages from
``scrapy.spidermiddlewares.httperror`` logger will be gone.

scrapy.utils.log module
=======================

.. module:: scrapy.utils.log
   :synopsis: Logging utils

.. autofunction:: configure_logging

    ``configure_logging`` is automatically called when using Scrapy commands,
    but needs to be called explicitly when running custom scripts. In that
    case, its usage is not required but it's recommended.

    If you plan on configuring the handlers yourself is still recommended you
    call this function, passing `install_root_handler=False`. Bear in mind
    there won't be any log output set by default in that case.

    To get you started on manually configuring logging's output, you can use
    `logging.basicConfig()`_ to set a basic root handler. This is an example
    on how to redirect ``INFO`` or higher messages to a file::

        import logging
        from scrapy.utils.log import configure_logging

        configure_logging(install_root_handler=False)
        logging.basicConfig(
            filename='log.txt',
            format='%(levelname)s: %(message)s',
            level=logging.INFO
        )

    Refer to :ref:`run-from-script` for more details about using Scrapy this
    way.

.. _logging.basicConfig(): https://docs.python.org/2/library/logging.html#logging.basicConfig


