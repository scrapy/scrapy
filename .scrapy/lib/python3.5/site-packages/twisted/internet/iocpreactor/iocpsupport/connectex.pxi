# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


def connect(long s, object addr, object obj):
    """
    CAUTION: unlike system ConnectEx(), this function returns 0 on success
    """
    cdef int family, rc
    cdef myOVERLAPPED *ov
    cdef sockaddr_in ipv4_name
    cdef sockaddr_in6 ipv6_name
    cdef sockaddr *name
    cdef int namelen

    if not have_connectex:
        raise ValueError, 'ConnectEx is not available on this system'

    family = getAddrFamily(s)
    if family == AF_INET:
        name = <sockaddr *>&ipv4_name
        namelen = sizeof(ipv4_name)
        fillinetaddr(&ipv4_name, addr)
    elif family == AF_INET6:
        name = <sockaddr *>&ipv6_name
        namelen = sizeof(ipv6_name)
        fillinet6addr(&ipv6_name, addr)
    else:
        raise ValueError, 'unsupported address family'
    name.sa_family = family

    ov = makeOV()
    if obj is not None:
        ov.obj = <PyObject *>obj

    rc = lpConnectEx(s, name, namelen, NULL, 0, NULL, <OVERLAPPED *>ov)

    if not rc:
        rc = WSAGetLastError()
        if rc != ERROR_IO_PENDING:
            PyMem_Free(ov)
            return rc

    # operation is in progress
    Py_XINCREF(obj)
    return 0

