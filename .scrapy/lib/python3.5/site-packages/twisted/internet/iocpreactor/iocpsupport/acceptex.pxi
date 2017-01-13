# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


def accept(long listening, long accepting, object buff, object obj):
    """
    CAUTION: unlike system AcceptEx(), this function returns 0 on success
    """
    cdef unsigned long bytes
    cdef int rc
    cdef Py_ssize_t size
    cdef void *mem_buffer
    cdef myOVERLAPPED *ov

    PyObject_AsWriteBuffer(buff, &mem_buffer, &size)

    ov = makeOV()
    if obj is not None:
        ov.obj = <PyObject *>obj

    rc = lpAcceptEx(listening, accepting, mem_buffer, 0,
                    <DWORD>size / 2, <DWORD>size / 2,
                    &bytes, <OVERLAPPED *>ov)
    if not rc:
        rc = WSAGetLastError()
        if rc != ERROR_IO_PENDING:
            PyMem_Free(ov)
            return rc

    # operation is in progress
    Py_XINCREF(obj)
    return 0

def get_accept_addrs(long s, object buff):
    cdef WSAPROTOCOL_INFO wsa_pi
    cdef int locallen, remotelen
    cdef Py_ssize_t size
    cdef void *mem_buffer
    cdef sockaddr *localaddr
    cdef sockaddr *remoteaddr

    PyObject_AsReadBuffer(buff, &mem_buffer, &size)

    lpGetAcceptExSockaddrs(mem_buffer, 0, <DWORD>size / 2, <DWORD>size / 2,
                           &localaddr, &locallen, &remoteaddr, &remotelen)
    return remoteaddr.sa_family, _makesockaddr(localaddr, locallen), _makesockaddr(remoteaddr, remotelen)

