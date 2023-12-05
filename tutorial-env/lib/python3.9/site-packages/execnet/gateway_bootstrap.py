"""
code to initialize the remote side of a gateway once the io is created
"""
import inspect
import os

import execnet

from . import gateway_base
from .gateway import Gateway

importdir = os.path.dirname(os.path.dirname(execnet.__file__))


class HostNotFound(Exception):
    pass


def bootstrap_import(io, spec):
    # only insert the importdir into the path if we must.  This prevents
    # bugs where backports expect to be shadowed by the standard library on
    # newer versions of python but would instead shadow the standard library
    sendexec(
        io,
        "import sys",
        "if %r not in sys.path:" % importdir,
        "    sys.path.insert(0, %r)" % importdir,
        "from execnet.gateway_base import serve, init_popen_io, get_execmodel",
        "sys.stdout.write('1')",
        "sys.stdout.flush()",
        "execmodel = get_execmodel(%r)" % spec.execmodel,
        "serve(init_popen_io(execmodel), id='%s-worker')" % spec.id,
    )
    s = io.read(1)
    assert s == b"1", repr(s)


def bootstrap_exec(io, spec):
    try:
        sendexec(
            io,
            inspect.getsource(gateway_base),
            "execmodel = get_execmodel(%r)" % spec.execmodel,
            "io = init_popen_io(execmodel)",
            "io.write('1'.encode('ascii'))",
            "serve(io, id='%s-worker')" % spec.id,
        )
        s = io.read(1)
        assert s == b"1"
    except EOFError:
        ret = io.wait()
        if ret == 255:
            raise HostNotFound(io.remoteaddress)


def bootstrap_socket(io, id):
    # XXX: switch to spec
    from execnet.gateway_socket import SocketIO

    sendexec(
        io,
        inspect.getsource(gateway_base),
        "import socket",
        inspect.getsource(SocketIO),
        "try: execmodel",
        "except NameError:",
        "   execmodel = get_execmodel('thread')",
        "io = SocketIO(clientsock, execmodel)",
        "io.write('1'.encode('ascii'))",
        "serve(io, id='%s-worker')" % id,
    )
    s = io.read(1)
    assert s == b"1"


def sendexec(io, *sources):
    source = "\n".join(sources)
    io.write((repr(source) + "\n").encode("utf-8"))


def fix_pid_for_jython_popen(gw):
    """
    fix for jython 2.5.1
    """
    spec, io = gw.spec, gw._io
    if spec.popen and not spec.via:
        # XXX: handle the case of remote being jython
        #      and not having the popen pid
        if io.popen.pid is None:
            io.popen.pid = gw.remote_exec(
                "import os; channel.send(os.getpid())"
            ).receive()


def bootstrap(io, spec):
    if spec.popen:
        if spec.via or spec.python:
            bootstrap_exec(io, spec)
        else:
            bootstrap_import(io, spec)
    elif spec.ssh or spec.vagrant_ssh:
        bootstrap_exec(io, spec)
    elif spec.socket:
        bootstrap_socket(io, spec)
    else:
        raise ValueError("unknown gateway type, can't bootstrap")
    gw = Gateway(io, spec)
    fix_pid_for_jython_popen(gw)
    return gw
