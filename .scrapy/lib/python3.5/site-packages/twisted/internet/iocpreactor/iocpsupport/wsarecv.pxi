# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


def recv(long s, object bufflist, object obj, unsigned long flags = 0):
    cdef int rc, res
    cdef myOVERLAPPED *ov
    cdef WSABUF *ws_buf
    cdef unsigned long bytes
    cdef PyObject **buffers
    cdef Py_ssize_t i, size, buffcount

    bufflist = PySequence_Fast(bufflist, 'second argument needs to be a list')
    buffcount = PySequence_Fast_GET_SIZE(bufflist)
    buffers = PySequence_Fast_ITEMS(bufflist)

    ws_buf = <WSABUF *>PyMem_Malloc(buffcount*sizeof(WSABUF))

    try:
        for i from 0 <= i < buffcount:
            PyObject_AsWriteBuffer(<object>buffers[i], <void **>&ws_buf[i].buf, &size)
            ws_buf[i].len = <DWORD>size

        ov = makeOV()
        if obj is not None:
            ov.obj = <PyObject *>obj

        rc = WSARecv(s, ws_buf, <DWORD>buffcount, &bytes, &flags, <OVERLAPPED *>ov, NULL)

        if rc == SOCKET_ERROR:
            rc = WSAGetLastError()
            if rc != ERROR_IO_PENDING:
                PyMem_Free(ov)
                return rc, 0

        Py_XINCREF(obj)
        return rc, bytes
    finally:
        PyMem_Free(ws_buf)

def recvfrom(long s, object buff, object addr_buff, object addr_len_buff, object obj, unsigned long flags = 0):
    cdef int rc, c_addr_buff_len, c_addr_len_buff_len
    cdef myOVERLAPPED *ov
    cdef WSABUF ws_buf
    cdef unsigned long bytes
    cdef sockaddr *c_addr_buff
    cdef int *c_addr_len_buff
    cdef Py_ssize_t size

    PyObject_AsWriteBuffer(buff, <void **>&ws_buf.buf, &size)
    ws_buf.len = <DWORD>size
    PyObject_AsWriteBuffer(addr_buff, <void **>&c_addr_buff, &size)
    c_addr_buff_len = <int>size
    PyObject_AsWriteBuffer(addr_len_buff, <void **>&c_addr_len_buff, &size)
    c_addr_len_buff_len = <int>size

    if c_addr_len_buff_len != sizeof(int):
        raise ValueError, 'length of address length buffer needs to be sizeof(int)'

    c_addr_len_buff[0] = c_addr_buff_len

    ov = makeOV()
    if obj is not None:
        ov.obj = <PyObject *>obj

    rc = WSARecvFrom(s, &ws_buf, 1, &bytes, &flags, c_addr_buff, c_addr_len_buff, <OVERLAPPED *>ov, NULL)

    if rc == SOCKET_ERROR:
        rc = WSAGetLastError()
        if rc != ERROR_IO_PENDING:
            PyMem_Free(ov)
            return rc, 0

    Py_XINCREF(obj)
    return rc, bytes

