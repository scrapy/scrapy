from collections import defaultdict
from logging import LogRecord
from typing import List, Union, Tuple, Sequence, Callable, Any, Optional
import atexit
import logging
import warnings
from pprint import pformat

from .comparison import SequenceComparison, compare
from .utils import wrap


class LogCapture(logging.Handler):
    """
    These are used to capture entries logged to the Python logging
    framework and make assertions about what was logged.

    :param names: A string (or tuple of strings) containing the dotted name(s)
                  of loggers to capture. By default, the root logger is
                  captured.

    :param install: If `True`, the :class:`LogCapture` will be
                    installed as part of its instantiation.

    :param propagate: If specified, any captured loggers will have their
                      `propagate` attribute set to the supplied value. This can
                      be used to prevent propagation from a child logger to a
                      parent logger that has configured handlers.

    :param attributes:

      The sequence of attribute names to return for each record or a callable
      that extracts a row from a record.

      If a sequence of attribute names, those attributes will be taken from the
      :class:`~logging.LogRecord`. If an attribute is callable, the value
      used will be the result of calling it. If an attribute is missing,
      ``None`` will be used in its place.

      If a callable, it will be called with the :class:`~logging.LogRecord`
      and the value returned will be used as the row.

    :param recursive_check:

      If ``True``, log messages will be compared recursively by
      :meth:`LogCapture.check`.

    :param ensure_checks_above:

      The log level above which checks must be made for logged events.
      See :meth:`ensure_checked`.

    """

    #: The records captured by this :class:`LogCapture`.
    records: List[LogRecord]
    #: The log level above which checks must be made for logged events.
    ensure_checks_above: Optional[int]

    instances = set()
    atexit_setup = False
    installed = False
    default_ensure_checks_above = logging.NOTSET

    def __init__(
            self,
            names: Union[str, Tuple[str]] = None,
            install: bool = True,
            level: int = 1,
            propagate: bool = None,
            attributes: Union[Sequence[str], Callable[[LogRecord], Any]] = (
                    'name', 'levelname', 'getMessage'
            ),
            recursive_check: bool = False,
            ensure_checks_above: int = None
    ):
        logging.Handler.__init__(self)
        if not isinstance(names, tuple):
            names = (names, )
        self.names = names
        self.level = level
        self.propagate = propagate
        self.attributes = attributes
        self.recursive_check = recursive_check
        self.old = defaultdict(dict)
        if ensure_checks_above is None:
            self.ensure_checks_above = self.default_ensure_checks_above
        else:
            self.ensure_checks_above = ensure_checks_above
        self.clear()
        if install:
            self.install()

    @classmethod
    def atexit(cls):
        if cls.instances:
            warnings.warn(
                'LogCapture instances not uninstalled by shutdown, '
                'loggers captured:\n'
                '%s' % ('\n'.join((str(i.names) for i in cls.instances)))
                )

    def __len__(self):
        return len(self.records)

    def __getitem__(self, index):
        return self._actual_row(self.records[index])

    def __contains__(self, what):
        for i, item in enumerate(self):
            if what == item:
                self.records[i].checked = True
                return True

    def clear(self):
        """Clear any entries that have been captured."""
        self.records = []

    def mark_all_checked(self):
        """
        Mark all captured events as checked.
        This should be called if you have made assertions about logging
        other than through :class:`LogCapture` methods.
        """
        for record in self.records:
            record.checked = True

    def ensure_checked(self, level: int = None):
        """
        Ensure every entry logged above the specified `level` has been checked.
        Raises an :class:`AssertionError` if this is not the case.

        :param level: the logging level, defaults to :attr:`ensure_checks_above`.
        """
        if level is None:
            level = self.ensure_checks_above
        if level == logging.NOTSET:
            return
        un_checked = []
        for record in self.records:
            if record.levelno >= level and not record.checked:
                un_checked.append(self._actual_row(record))
        if un_checked:
            raise AssertionError((
                    'Not asserted ERROR log(s): %s'
                ) % (pformat(un_checked)))

    def emit(self, record: logging.LogRecord):
        """
        Record the :class:`~logging.LogRecord`.
        """
        record.checked = False
        self.records.append(record)

    def install(self):
        """
        Install this :class:`LogCapture` into the Python logging
        framework for the named loggers.

        This will remove any existing handlers for those loggers and
        drop their level to that specified on this :class:`LogCapture` in order
        to capture all logging.
        """
        for name in self.names:
            logger = logging.getLogger(name)
            self.old['levels'][name] = logger.level
            self.old['filters'][name] = logger.filters
            self.old['handlers'][name] = logger.handlers
            self.old['disabled'][name] = logger.disabled
            self.old['propagate'][name] = logger.propagate
            logger.setLevel(self.level)
            logger.filters = []
            logger.handlers = [self]
            logger.disabled = False
            if self.propagate is not None:
                logger.propagate = self.propagate
        self.instances.add(self)
        if not self.__class__.atexit_setup:
            atexit.register(self.atexit)
            self.__class__.atexit_setup = True

    def uninstall(self):
        """
        Un-install this :class:`LogCapture` from the Python logging
        framework for the named loggers.

        This will re-instate any existing handlers for those loggers
        that were removed during installation and restore their level
        that prior to installation.
        """
        if self in self.instances:
            for name in self.names:
                logger = logging.getLogger(name)
                logger.setLevel(self.old['levels'][name])
                logger.filters = self.old['filters'][name]
                logger.handlers = self.old['handlers'][name]
                logger.disabled = self.old['disabled'][name]
                logger.propagate = self.old['propagate'][name]
            self.instances.remove(self)

    @classmethod
    def uninstall_all(cls):
        "This will uninstall all existing :class:`LogCapture` objects."
        for i in tuple(cls.instances):
            i.uninstall()

    def _actual_row(self, record):
        # Convert a log record to a Tuple or attribute value according the attributes member.
        # record: logging.LogRecord

        if callable(self.attributes):
            return self.attributes(record)
        else:
            values = []
            for a in self.attributes:
                value = getattr(record, a, None)
                if callable(value):
                    value = value()
                values.append(value)
            if len(values) == 1:
                return values[0]
            else:
                return tuple(values)

    def actual(self) -> List:
        """
        The sequence of actual records logged, having had their attributes
        extracted as specified by the ``attributes`` parameter to the
        :class:`LogCapture` constructor.

        This can be useful for making more complex assertions about logged
        records. The actual records logged can also be inspected by using the
        :attr:`records` attribute.
        """
        actual = []
        for r in self.records:
            actual.append(self._actual_row(r))
        return actual

    def __str__(self):
        if not self.records:
            return 'No logging captured'
        return '\n'.join(["%s %s\n  %s" % r for r in self.actual()])

    def check(self, *expected):
        """
        This will compare the captured entries with the expected
        entries provided and raise an :class:`AssertionError` if they
        do not match.

        :param expected:

          A sequence of entries of the structure specified by the ``attributes``
          passed to the constructor.
        """
        compare(
            expected,
            actual=self.actual(),
            recursive=self.recursive_check
            )
        self.mark_all_checked()

    def check_present(self, *expected, order_matters: bool = True):
        """
        This will check if the captured entries contain all of the expected
        entries provided and raise an :class:`AssertionError` if not.
        This will ignore entries that have been captured but that do not
        match those in ``expected``.

        :param expected:

          A sequence of entries of the structure specified by the ``attributes``
          passed to the constructor.

        :param order_matters:

          A keyword-only parameter that controls whether the order of the
          captured entries is required to match those of the expected entries.
          Defaults to ``True``.
        """
        actual = self.actual()
        expected = SequenceComparison(
            *expected, ordered=order_matters, partial=True, recursive=self.recursive_check
        )
        if expected != actual:
            raise AssertionError(expected.failed)
        for index in expected.checked_indices:
            self.records[index].checked = True

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.uninstall()
        self.ensure_checked()


class LogCaptureForDecorator(LogCapture):

    def install(self):
        LogCapture.install(self)
        self.clear()
        return self


def log_capture(*names: str, **kw):
    """
    A decorator for making a :class:`LogCapture` installed and
    available for the duration of a test function.

    :param names: An optional sequence of names specifying the loggers
                  to be captured. If not specified, the root logger
                  will be captured.

    Keyword parameters other than ``install`` may also be supplied and will be
    passed on to the :class:`LogCapture` constructor.
    """
    l = LogCaptureForDecorator(names or None, install=False, **kw)
    return wrap(l.install, l.uninstall)
