"""
Managing Gateway Groups and interactions with multiple channels.

(c) 2008-2014, Holger Krekel and others
"""
import atexit
import sys
from functools import partial
from threading import Lock

from . import gateway_bootstrap
from . import gateway_io
from .gateway_base import get_execmodel
from .gateway_base import trace
from .gateway_base import WorkerPool
from .xspec import XSpec

NO_ENDMARKER_WANTED = object()


class Group:
    """Gateway Groups."""

    defaultspec = "popen"

    def __init__(self, xspecs=(), execmodel="thread"):
        """initialize group and make gateways as specified.
        execmodel can be 'thread' or 'eventlet'.
        """
        self._gateways = []
        self._autoidcounter = 0
        self._autoidlock = Lock()
        self._gateways_to_join = []
        # we use the same execmodel for all of the Gateway objects
        # we spawn on our side.  Probably we should not allow different
        # execmodels between different groups but not clear.
        # Note that "other side" execmodels may differ and is typically
        # specified by the spec passed to makegateway.
        self.set_execmodel(execmodel)
        for xspec in xspecs:
            self.makegateway(xspec)
        atexit.register(self._cleanup_atexit)

    @property
    def execmodel(self):
        return self._execmodel

    @property
    def remote_execmodel(self):
        return self._remote_execmodel

    def set_execmodel(self, execmodel, remote_execmodel=None):
        """Set the execution model for local and remote site.

        execmodel can be one of "thread" or "eventlet" (XXX gevent).
        It determines the execution model for any newly created gateway.
        If remote_execmodel is not specified it takes on the value
        of execmodel.

        NOTE: Execution models can only be set before any gateway is created.

        """
        if self._gateways:
            raise ValueError(
                "can not set execution models if " "gateways have been created already"
            )
        if remote_execmodel is None:
            remote_execmodel = execmodel
        self._execmodel = get_execmodel(execmodel)
        self._remote_execmodel = get_execmodel(remote_execmodel)

    def __repr__(self):
        idgateways = [gw.id for gw in self]
        return "<Group %r>" % idgateways

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._gateways[key]
        for gw in self._gateways:
            if gw == key or gw.id == key:
                return gw
        raise KeyError(key)

    def __contains__(self, key):
        try:
            self[key]
            return True
        except KeyError:
            return False

    def __len__(self):
        return len(self._gateways)

    def __iter__(self):
        return iter(list(self._gateways))

    def makegateway(self, spec=None):
        """create and configure a gateway to a Python interpreter.
        The ``spec`` string encodes the target gateway type
        and configuration information. The general format is::

            key1=value1//key2=value2//...

        If you leave out the ``=value`` part a True value is assumed.
        Valid types: ``popen``, ``ssh=hostname``, ``socket=host:port``.
        Valid configuration::

            id=<string>     specifies the gateway id
            python=<path>   specifies which python interpreter to execute
            execmodel=model 'thread', 'eventlet', 'gevent' model for execution
            chdir=<path>    specifies to which directory to change
            nice=<path>     specifies process priority of new process
            env:NAME=value  specifies a remote environment variable setting.

        If no spec is given, self.defaultspec is used.
        """
        if not spec:
            spec = self.defaultspec
        if not isinstance(spec, XSpec):
            spec = XSpec(spec)
        self.allocate_id(spec)
        if spec.execmodel is None:
            spec.execmodel = self.remote_execmodel.backend
        if spec.via:
            assert not spec.socket
            master = self[spec.via]
            proxy_channel = master.remote_exec(gateway_io)
            proxy_channel.send(vars(spec))
            proxy_io_master = gateway_io.ProxyIO(proxy_channel, self.execmodel)
            gw = gateway_bootstrap.bootstrap(proxy_io_master, spec)
        elif spec.popen or spec.ssh or spec.vagrant_ssh:
            io = gateway_io.create_io(spec, execmodel=self.execmodel)
            gw = gateway_bootstrap.bootstrap(io, spec)
        elif spec.socket:
            from . import gateway_socket

            io = gateway_socket.create_io(spec, self, execmodel=self.execmodel)
            gw = gateway_bootstrap.bootstrap(io, spec)
        else:
            raise ValueError(f"no gateway type found for {spec._spec!r}")
        gw.spec = spec
        self._register(gw)
        if spec.chdir or spec.nice or spec.env:
            channel = gw.remote_exec(
                """
                import os
                path, nice, env = channel.receive()
                if path:
                    if not os.path.exists(path):
                        os.mkdir(path)
                    os.chdir(path)
                if nice and hasattr(os, 'nice'):
                    os.nice(nice)
                if env:
                    for name, value in env.items():
                        os.environ[name] = value
            """
            )
            nice = spec.nice and int(spec.nice) or 0
            channel.send((spec.chdir, nice, spec.env))
            channel.waitclose()
        return gw

    def allocate_id(self, spec):
        """(re-entrant) allocate id for the given xspec object."""
        if spec.id is None:
            with self._autoidlock:
                id = "gw" + str(self._autoidcounter)
                self._autoidcounter += 1
                if id in self:
                    raise ValueError(f"already have gateway with id {id!r}")
                spec.id = id

    def _register(self, gateway):
        assert not hasattr(gateway, "_group")
        assert gateway.id
        assert gateway.id not in self
        self._gateways.append(gateway)
        gateway._group = self

    def _unregister(self, gateway):
        self._gateways.remove(gateway)
        self._gateways_to_join.append(gateway)

    def _cleanup_atexit(self):
        trace(f"=== atexit cleanup {self!r} ===")
        self.terminate(timeout=1.0)

    def terminate(self, timeout=None):
        """trigger exit of member gateways and wait for termination
        of member gateways and associated subprocesses.  After waiting
        timeout seconds try to to kill local sub processes of popen-
        and ssh-gateways.  Timeout defaults to None meaning
        open-ended waiting and no kill attempts.
        """

        while self:
            vias = {}
            for gw in self:
                if gw.spec.via:
                    vias[gw.spec.via] = True
            for gw in self:
                if gw.id not in vias:
                    gw.exit()

            def join_wait(gw):
                gw.join()
                gw._io.wait()

            def kill(gw):
                trace("Gateways did not come down after timeout: %r" % gw)
                gw._io.kill()

            safe_terminate(
                self.execmodel,
                timeout,
                [
                    (partial(join_wait, gw), partial(kill, gw))
                    for gw in self._gateways_to_join
                ],
            )
            self._gateways_to_join[:] = []

    def remote_exec(self, source, **kwargs):
        """remote_exec source on all member gateways and return
        MultiChannel connecting to all sub processes.
        """
        channels = []
        for gw in self:
            channels.append(gw.remote_exec(source, **kwargs))
        return MultiChannel(channels)


class MultiChannel:
    def __init__(self, channels):
        self._channels = channels

    def __len__(self):
        return len(self._channels)

    def __iter__(self):
        return iter(self._channels)

    def __getitem__(self, key):
        return self._channels[key]

    def __contains__(self, chan):
        return chan in self._channels

    def send_each(self, item):
        for ch in self._channels:
            ch.send(item)

    def receive_each(self, withchannel=False):
        assert not hasattr(self, "_queue")
        l = []
        for ch in self._channels:
            obj = ch.receive()
            if withchannel:
                l.append((ch, obj))
            else:
                l.append(obj)
        return l

    def make_receive_queue(self, endmarker=NO_ENDMARKER_WANTED):
        try:
            return self._queue
        except AttributeError:
            self._queue = None
            for ch in self._channels:
                if self._queue is None:
                    self._queue = ch.gateway.execmodel.queue.Queue()

                def putreceived(obj, channel=ch):
                    self._queue.put((channel, obj))

                if endmarker is NO_ENDMARKER_WANTED:
                    ch.setcallback(putreceived)
                else:
                    ch.setcallback(putreceived, endmarker=endmarker)
            return self._queue

    def waitclose(self):
        first = None
        for ch in self._channels:
            try:
                ch.waitclose()
            except ch.RemoteError:
                if first is None:
                    first = sys.exc_info()
        if first:
            raise first[1].with_traceback(first[2])


def safe_terminate(execmodel, timeout, list_of_paired_functions):
    workerpool = WorkerPool(execmodel)

    def termkill(termfunc, killfunc):
        termreply = workerpool.spawn(termfunc)
        try:
            termreply.get(timeout=timeout)
        except OSError:
            killfunc()

    replylist = []
    for termfunc, killfunc in list_of_paired_functions:
        reply = workerpool.spawn(termkill, termfunc, killfunc)
        replylist.append(reply)
    for reply in replylist:
        reply.get()
    workerpool.waitall(timeout=timeout)


default_group = Group()
makegateway = default_group.makegateway
set_execmodel = default_group.set_execmodel
