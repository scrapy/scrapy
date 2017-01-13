# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


def send(long s, object buff, object obj, unsigned long flags = 0):
    cdef int rc
    cdef myOVERLAPPED *ov
    cdef WSABUF ws_buf
    cdef unsigned long bytes
    cdef Py_ssize_t size

    PyObject_AsReadBuffer(buff, <void **>&ws_buf.buf, &size)
    ws_buf.len = <DWORD>size

    ov = makeOV()
    if obj is not None:
        ov.obj = <PyObject *>obj

    rc = WSASend(s, &ws_buf, 1, &bytes, flags, <OVERLAPPED *>ov, NULL)

    if rc == SOCKET_ERROR:
        rc = WSAGetLastError()
        if rc != ERROR_IO_PENDING:
            PyMem_Free(ov)
            return rc, bytes

    Py_XINCREF(obj)
    return rc, bytes


