# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

#
from twisted.conch.client import direct

connectTypes = {"direct": direct.connect}


def connect(host, port, options, verifyHostKey, userAuthObject):
    useConnects = ["direct"]
    return _ebConnect(
        None, useConnects, host, port, options, verifyHostKey, userAuthObject
    )


def _ebConnect(f, useConnects, host, port, options, vhk, uao):
    if not useConnects:
        return f
    connectType = useConnects.pop(0)
    f = connectTypes[connectType]
    d = f(host, port, options, vhk, uao)
    d.addErrback(_ebConnect, useConnects, host, port, options, vhk, uao)
    return d
