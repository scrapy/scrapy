import sys
import threading
import warnings
import weakref
import logging

import six
from six.moves import range
from twisted.internet.defer import maybeDeferred, DeferredList, Deferred
from twisted.python.failure import Failure

from scrapy.utils.log import failure_to_exc_info
from scrapy.dispatch.utils.inspect import func_accepts_kwargs
from scrapy.dispatch.utils import robust_apply
from scrapy.exceptions import ScrapyDeprecationWarning
if six.PY2 or sys.version_info >= (3, 3) and sys.version_info < (3, 4):
    from .weakref_backports import WeakMethod
else:
    from weakref import WeakMethod


def _make_id(target):
    if hasattr(target, '__func__'):
        return (id(target.__self__), id(target.__func__))
    return id(target)
NONE_ID = _make_id(None)

logger = logging.getLogger(__name__)

# A marker for caching
NO_RECEIVERS = object()


class _IgnoredException(Exception):
    pass


class Signal(object):

    """Base class for all signals"""

    def __init__(self, providing_args=None, use_caching=False):
        """
        Create a new signal.

        :param providing_args
            A list of the arguments this signal can pass along in a send()
            call.
        """
        self.receivers = []
        if providing_args is None:
            providing_args = []
        self.providing_args = set(providing_args)
        self.lock = threading.Lock()
        self.use_caching = use_caching
        # For convenience we create empty caches even if they are not used.
        # A note about caching: if use_caching is defined, then for each
        # distinct sender we cache the receivers that sender has in
        # 'sender_receivers_cache'. The cache is cleaned when .connect() or
        # .disconnect() is called and populated on send().
        self.sender_receivers_cache = weakref.WeakKeyDictionary(
        ) if use_caching else {}
        self.receiver_accepts_kwargs = {}
        self._dead_receivers = False

    def connect(self, receiver, sender=None, weak=True, dispatch_uid=None):
        """
        Connect receiver to sender for signal.

        :param receiver: A function or an instance method which is
                         to receive signals. If a receiver is connected
                         with a dispatch_uid argument, it will not be added
                         if another receiver was already connected that
                         dispatch_uid.
        :type receiver: function or instance, must be hashable object with

        :param sender: The sender to which the receiver should respond.
                       Must either be a Python object, or None to receive
                       events from any sender.
        :type sender: object, None

        :param weak: Whether to use weak references to the receiver. By
                     default, the module will attempt to use weak
                     references to the receiver objects. If this parameter
                     is false, then strong references will be used.
        :type weak: Boolean

        :param dispatch_uid: An identifier used to uniquely identify a
                             particular instance of a receiver.
        :type dispatch_uid: string, though it may be anything
                            hashable.
        """
        assert callable(receiver), "Signal receivers must be callable."
        # Check for **kwargs
        accepts_kwargs = True
        if not func_accepts_kwargs(receiver):
            warnings.warn("The use of handlers that don't accept "
                          "**kwargs has been deprecated, plese refer "
                          "to the Signals API documentation.",
                          ScrapyDeprecationWarning, stacklevel=3)
            accepts_kwargs = False
        if dispatch_uid:
            lookup_key = (dispatch_uid, _make_id(sender))
        else:
            lookup_key = (_make_id(receiver), _make_id(sender))
        accepts_kwargs_lookup = _make_id(receiver)
        if weak:
            ref = weakref.ref
            receiver_object = receiver
            # Check for bound methods
            if hasattr(receiver, '__self__') and hasattr(receiver, '__func__'):
                ref = WeakMethod
                receiver_object = receiver.__self__
            if six.PY3 and sys.version_info >= (3, 4):
                receiver = ref(receiver)
                weakref.finalize(receiver_object, self._remove_receiver)
            else:
                receiver = ref(receiver, self._remove_receiver)

        with self.lock:
            self._clear_dead_receivers()
            for r_key, _ in self.receivers:
                if r_key == lookup_key:
                    break
            else:
                self.receivers.append((lookup_key, receiver))
                self.receiver_accepts_kwargs[accepts_kwargs_lookup] = accepts_kwargs
            self.sender_receivers_cache.clear()

    def disconnect(self, receiver=None, sender=None, dispatch_uid=None):
        """
        Disconnect receiver from sender for signal.

        If weak references are used, disconnect need not be called. The
        receiver will be remove from dispatch automatically.

        :param receiver: The registered receiver to disconnect. May be none if
                         dispatch_uid is specified.
        :type receiver: A function or an instance method which was registered
                        to receive signals.

        :param sender: The registered sender to disconnect
        :type sender: Any python object, registered as a sender using connect
                      previously.

        :param dispatch_uid: The unique identifier of the receiver to
                             disconnect
        :type dispatch_uid: string, though it may be anything hashable.

        :return: True if disconnected, False in case of no disconnection due to
                 receiver being disconnected alraedy, etc.
        """
        if dispatch_uid:
            lookup_key = (dispatch_uid, _make_id(sender))
        else:
            lookup_key = (_make_id(receiver), _make_id(sender))

        disconnected = False
        with self.lock:
            self._clear_dead_receivers()
            for index in range(len(self.receivers)):
                (r_key, _) = self.receivers[index]
                if r_key == lookup_key:
                    disconnected = True
                    del self.receivers[index]
                    break
            self.sender_receivers_cache.clear()
            if disconnected:
                self.receiver_accepts_kwargs.pop(_make_id(receiver), None)
        return disconnected

    def has_listeners(self, sender=None):
        return bool(self._live_receivers(sender))

    def disconnect_all(self, sender=None):
        for receiver in self._live_receivers(sender=sender):
            self.disconnect(receiver=receiver, sender=sender)

    def send(self, sender, **named):
        """
        Send signal from sender to all connected receivers.

        If any receiver raises an error, the error propagates back through
        send, terminating the dispatch loop. So it's possible that all
        receivers won't be called if an error is raised.

        :param sender: The sender of the signal.
                       Either a specific object or None.


        :param dict named:   Named arguments which will be passed to
                             receivers, These arguments must be a subset of
                             the argument names defined in providing_args.

        Returns a list of tuple pairs [(receiver, response), ... ].
        """
        responses = []
        if not self.receivers or \
                self.sender_receivers_cache.get(sender) is NO_RECEIVERS:
            return responses
        for receiver in self._live_receivers(sender):
            if self.receiver_accepts_kwargs[_make_id(receiver)]:
                response = receiver(signal=self, sender=sender, **named)
            else:
                response = robust_apply(receiver, signal=self,
                                        sender=sender, **named)
            responses.append((receiver, response))
        return responses

    def send_catch_log(self, sender, **named):
        """
        Send signal from sender to all connected receivers catching and logging
        errors.

        If any receiver raises an error, it is caught and logged before
        returning a ``twisted.python.Failure`` instance.

        More robust than send in that even if an error is encountered, all
        receivers will still be called.

        The receivers here cannot return deferred instances.

        :param sender: The sender of the signal.
        :type sender: Can be any python object (normally one registered with a
                      connect if you actually want something to occur).

        :param dict named:  Named arguments which will be passed to receivers.
                            These arguments must be a subset of the argument
                            names defined in providing_args.

        :return: A list of tuple pairs [(receiver, response), ... ].
        """
        dont_log = named.pop('dont_log', _IgnoredException)
        spider = named.get('spider', None)
        responses = []
        if not self.receivers or \
                self.sender_receivers_cache.get(sender) is NO_RECEIVERS:
            return responses
        # Call each receiver with whatever arguments it can accept.
        # Return a list of tuple pairs [(receiver, response), ... ].
        for receiver in self._live_receivers(sender):
            try:
                if self.receiver_accepts_kwargs[_make_id(receiver)]:
                    response = receiver(signal=self, sender=sender, **named)
                else:
                    response = robust_apply(receiver, signal=self,
                                            sender=sender, **named)
                if isinstance(response, Deferred):
                    logger.error("Cannot return deferreds from signal"
                                 " handler: %(receiver)s",
                                 {'receiver': receiver},
                                 extra={'spider': spider})
            except dont_log:
                response = Failure()
            except Exception:
                response = Failure()
                logger.error("Error caught on signal handler: %(receiver)s",
                             {'receiver': receiver},
                             exc_info=True, extra={'spider': spider})
            responses.append((receiver, response))
        return responses

    def send_catch_log_deferred(self, sender, **named):
        """
        Send signal from sender to all connected receivers catching and logging
        errors. Works with receivers that return twisted `deferred`_
        instances.

        :param sender: The sender of the signal.
        :type sender: Any python object, normally one registered with a connect
                      if you actually want something to occur.

        :param dict named: Named arguments which will be passed to receivers.
                           These arguments must be a subset of the argument
                           names defined in providing_args.

        :return: a DeferredList instance that fires with a list of tuple
                 pairs of the form [(receiver, response)..].

        .. _deferred: http://twistedmatrix.com/documents/current/core/howto/defer.html # noqa
        """
        dont_log = named.pop('dont_log', _IgnoredException)
        def logerror(failure, recv):
            spider = named.get('spider', None)
            if dont_log is None or not isinstance(failure.value, dont_log):
                logger.error("Error caught on signal handler: %(receiver)s",
                             {'receiver': recv},
                             exc_info=failure_to_exc_info(failure),
                             extra={'spider': spider})
            return failure
        dfds = []
        if not self.receivers or \
                self.sender_receivers_cache.get(sender) is NO_RECEIVERS:
            return dfds
        # Call each receiver with whatever arguments it can accept.
        # Return a list of tuple pairs [(receiver, response), ... ].
        for receiver in self._live_receivers(sender):
            dfd = maybeDeferred(
                receiver,  signal=self, sender=sender, **named)
            dfd.addErrback(logerror, receiver)
            dfd.addBoth(lambda result: (receiver, result))
            dfds.append(dfd)
        d = DeferredList(dfds)
        d.addCallback(lambda out: [x[1] for x in out])
        return d

    def _clear_dead_receivers(self):
        # Note: caller is assumed to hold self.lock.
        if self._dead_receivers:
            self._dead_receivers = False
            new_receivers = []
            for r in self.receivers:
                if not(isinstance(r[1], weakref.ReferenceType) and
                        r[1]() is None):
                    new_receivers.append(r)
                else:
                    self.receiver_accepts_kwargs.pop(r[0][0], None)
            self.receivers = new_receivers

    def _live_receivers(self, sender):
        """
        Filter sequence of receivers to get resolved, live receivers.

        This checks for weak references and resolves them, then returning only
        live receivers.
        """
        receivers = None
        if self.use_caching and not self._dead_receivers:
            receivers = self.sender_receivers_cache.get(sender)
            # We could end up here with NO_RECEIVERS even if we do check
            # this case in .send() prior to calling _live_receivers() due to
            # concurrent .send() call.
            if receivers is NO_RECEIVERS:
                return []
        if receivers is None:
            with self.lock:
                self._clear_dead_receivers()
                senderkey = _make_id(sender)
                receivers = []
                for (receiverkey, r_senderkey), receiver in self.receivers:
                    if r_senderkey == NONE_ID or r_senderkey == senderkey:
                        receivers.append(receiver)
                if self.use_caching:
                    if not receivers:
                        self.sender_receivers_cache[sender] = NO_RECEIVERS
                    else:
                        # Note, we must cache the weakref versions.
                        self.sender_receivers_cache[sender] = receivers
        non_weak_receivers = []
        for receiver in receivers:
            if isinstance(receiver, weakref.ReferenceType):
                # Dereference the weak reference.
                receiver = receiver()
                if receiver is not None:
                    non_weak_receivers.append(receiver)
            else:
                non_weak_receivers.append(receiver)
        return non_weak_receivers

    def _remove_receiver(self, receiver=None):
        # Mark that the self.receivers list has dead weakrefs. If so, we will
        # clean those up in connect, disconnect and _live_receivers while
        # holding self.lock. Note that doing the cleanup here isn't a good
        # idea, _remove_receiver() will be called as side effect of garbage
        # collection, and so the call can happen while we are already holding
        # self.lock.
        self._dead_receivers = True


def receiver(signal, **kwargs):
    """
    A decorator for connecting receivers to signals. Used by passing in the
    signal (or list of signals) and keyword arguments to connect::

        @receiver(spider_closed, sender=None)
        def signal_receiver(sender, **kwargs):
            ...

        @receiver([spider_closed, engine_stopped], sender=spider)
        def signals_receiver(sender, **kwargs):
            ...
    """
    def _decorator(func):
        if isinstance(signal, (list, tuple)):
            for s in signal:
                s.connect(func, **kwargs)
        else:
            signal.connect(func, **kwargs)
        return func
    return _decorator
