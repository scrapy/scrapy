from __future__ import annotations

from logging import Formatter
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from scrapy.settings import Settings


class LogRootFormatterProtocol(Protocol):
    """Protocol for log root formatters.

    Besides the ``__init__`` method below, classes implementing this protocol
    must either subclass :class:`~logging.Formatter` or implement its API.

    Mind that, during a crawl, Scrapy usually creates 2 instances of the log
    root formatter:

    1.  One early on with only the project *settings*.

    2.  Another one later on, where *settings* also includes add-on and spider
        settings.

        If you are using multiple :class:`~scrapy.crawler.Crawler` objects, 1
        log root formatter instance will be created for each crawler.
    """

    def __init__(self, settings: Settings) -> None: ...


class LogRootFormatter(Formatter):
    """Default :setting:`LOG_ROOT_FORMATTER`.

    Allows customizing log formatting with the following settings.

    .. note:: Alternative log root formatters are encouraged, but not required,
        to support these settings.

    .. setting:: LOG_FORMAT

    LOG_FORMAT
    ----------

    Default: ``'%(asctime)s [%(name)s] %(levelname)s: %(message)s'``

    String for formatting log messages. Refer to the :ref:`Python logging
    documentation <logrecord-attributes>` for the whole list of available
    placeholders, plus ``%(spider)s`` for the name of the spider that
    triggered the log message, or ``"-"`` for messages not tied to a spider
    (see :ref:`topics-logging-from-spiders`).

    .. note:: This is a :ref:`logging setting <logging-settings>`.

    .. setting:: LOG_DATEFORMAT

    LOG_DATEFORMAT
    --------------

    Default: ``'%Y-%m-%d %H:%M:%S'``

    String for formatting date/time, expansion of the ``%(asctime)s``
    placeholder in :setting:`LOG_FORMAT`. Refer to the :ref:`Python datetime
    documentation <strftime-strptime-behavior>` for the whole list of available
    directives.

    .. note:: This is a :ref:`logging setting <logging-settings>`.
    """

    def __init__(self, settings: Settings):
        super().__init__(fmt=settings["LOG_FORMAT"], datefmt=settings["LOG_DATEFORMAT"])
