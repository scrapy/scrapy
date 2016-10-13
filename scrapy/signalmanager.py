from __future__ import absolute_import
import warnings

from scrapy.dispatch import Signal
from scrapy.exceptions import ScrapyDeprecationWarning


class SignalManager(object):

    def __init__(self, sender=None):
        self.sender = sender
        self._signal_proxies = {}

    def _ensure_signal(self, signal):
        """
        This method is for backward compatability for any custom signals
        that might be in use in third party extensions which is still using the
        standard python objects as signals. This method returns a Signal()
        class instance and saves it to proxy the user defined signal.
        """
        if isinstance(signal, Signal):
            return signal
        warnings.warn("Signals in scrapy are no longer instances of the "
                      "generic python object rather should be instances of "
                      "`scrapy.dispatch.Signal`. Please refer to the "
                      "Signal API documentation for more information.",
                      ScrapyDeprecationWarning, stacklevel=2)
        return self._signal_proxies.setdefault(signal, Signal())

    def connect(self, receiver, signal, **kwargs):
        """
        Connect a receiver function to a signal.

        The signal can be any object, although Scrapy comes with some
        predefined signals that are documented in the :ref:`topics-signals`
        section.

        :param receiver: the function to be connected
        :type receiver: callable

        :param signal: the signal to connect to
        :type signal: object

        :param weak: Whether to use a weak reference to this receiver
        :type weak: boolean
        """
        kwargs.setdefault('sender', self.sender)
        signal = self._ensure_signal(signal)
        return signal.connect(receiver, **kwargs)

    def disconnect(self, receiver, signal, **kwargs):
        """
        Disconnect a receiver function from a signal. This has the
        opposite effect of the :meth:`connect` method, and the arguments
        are the same.
        """
        kwargs.setdefault('sender', self.sender)
        signal = self._ensure_signal(signal)
        return signal.disconnect(receiver, **kwargs)

    def send_catch_log(self, signal, **kwargs):
        """
        Send a signal, catch exceptions and log them.

        The keyword arguments are passed to the signal handlers (connected
        through the :meth:`connect` method).
        """
        kwargs.setdefault('sender', self.sender)
        signal = self._ensure_signal(signal)
        return signal.send_catch_log(**kwargs)

    def send_catch_log_deferred(self, signal, **kwargs):
        """
        Like :meth:`send_catch_log` but supports returning `deferreds`_ from
        signal handlers.

        Returns a Deferred that gets fired once all signal handlers
        deferreds were fired. Send a signal, catch exceptions and log them.

        The keyword arguments are passed to the signal handlers (connected
        through the :meth:`connect` method).

        .. _deferreds: http://twistedmatrix.com/documents/current/core/howto/defer.html
        """
        kwargs.setdefault('sender', self.sender)
        signal = self._ensure_signal(signal)
        return signal.send_catch_log_deferred(**kwargs)

    def disconnect_all(self, signal, **kwargs):
        """
        Disconnect all receivers from the given signal.

        :param signal: the signal to disconnect from
        :type signal: object
        """
        kwargs.setdefault('sender', self.sender)
        signal = self._ensure_signal(signal)
        return signal.disconnect_all(**kwargs)
