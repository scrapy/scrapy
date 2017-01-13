/*
 * Copyright (c) Twisted Matrix Laboratories.
 * See LICENSE for details.
 */

#define PY_SSIZE_T_CLEAN 1
#include <Python.h>

#if PY_VERSION_HEX < 0x02050000 && !defined(PY_SSIZE_T_MIN)
/* This may cause some warnings, but if you want to get rid of them, upgrade
 * your Python version.  */
typedef int Py_ssize_t;
#endif

#include <sys/types.h>
#include <sys/socket.h>
#include <signal.h>

#include <sys/param.h>

#ifdef BSD
#include <sys/uio.h>
#endif

/*
 * As per
 * <http://pubs.opengroup.org/onlinepubs/007904875/basedefs/sys/socket.h.html
 * #tag_13_61_05>:
 *
 *     "To forestall portability problems, it is recommended that applications
 *     not use values larger than (2**31)-1 for the socklen_t type."
 */

#define SOCKLEN_MAX 0x7FFFFFFF

PyObject *sendmsg_socket_error;

static PyObject *sendmsg_sendmsg(PyObject *self, PyObject *args, PyObject *keywds);
static PyObject *sendmsg_recvmsg(PyObject *self, PyObject *args, PyObject *keywds);
static PyObject *sendmsg_getsockfam(PyObject *self, PyObject *args, PyObject *keywds);

static char sendmsg_doc[] = "\
Bindings for sendmsg(2), recvmsg(2), and a minimal helper for inspecting\n\
address family of a socket.\n\
";

static char sendmsg_sendmsg_doc[] = "\
Wrap the C sendmsg(2) function for sending \"messages\" on a socket.\n\
\n\
@param fd: The file descriptor of the socket over which to send a message.\n\
@type fd: C{int}\n\
\n\
@param data: Bytes to write to the socket.\n\
@type data: C{str}\n\
\n\
@param flags: Flags to affect how the message is sent.  See the C{MSG_}\n\
    constants in the sendmsg(2) manual page.  By default no flags are set.\n\
@type flags: C{int}\n\
\n\
@param ancillary: Extra data to send over the socket outside of the normal\n\
    datagram or stream mechanism.  By default no ancillary data is sent.\n\
@type ancillary: C{list} of C{tuple} of C{int}, C{int}, and C{str}.\n\
\n\
@raise OverflowError: Raised if too much ancillary data is given.\n\
@raise socket.error: Raised if the underlying syscall indicates an error.\n\
\n\
@return: The return value of the underlying syscall, if it succeeds.\n\
";

static char sendmsg_recvmsg_doc[] = "\
Wrap the C recvmsg(2) function for receiving \"messages\" on a socket.\n\
\n\
@param fd: The file descriptor of the socket over which to receive a message.\n\
@type fd: C{int}\n\
\n\
@param flags: Flags to affect how the message is sent.  See the C{MSG_}\n\
    constants in the sendmsg(2) manual page.  By default no flags are set.\n\
@type flags: C{int}\n\
\n\
@param maxsize: The maximum number of bytes to receive from the socket\n\
    using the datagram or stream mechanism.  The default maximum is 8192.\n\
@type maxsize: C{int}\n\
\n\
@param cmsg_size: The maximum number of bytes to receive from the socket\n\
    outside of the normal datagram or stream mechanism.  The default maximum is 4096.\n\
\n\
@raise OverflowError: Raised if too much ancillary data is given.\n\
@raise socket.error: Raised if the underlying syscall indicates an error.\n\
\n\
@return: A C{tuple} of three elements: the bytes received using the\n\
    datagram/stream mechanism, flags as an C{int} describing the data\n\
    received, and a C{list} of C{tuples} giving ancillary received data.\n\
";

static char sendmsg_getsockfam_doc[] = "\
Retrieve the address family of a given socket.\n\
\n\
@param fd: The file descriptor of the socket the address family of which\n\
    to retrieve.\n\
@type fd: C{int}\n\
\n\
@raise socket.error: Raised if the underlying getsockname call indicates\n\
    an error.\n\
\n\
@return: A C{int} representing the address family of the socket.  For\n\
    example, L{socket.AF_INET}, L{socket.AF_INET6}, or L{socket.AF_UNIX}.\n\
";

static PyMethodDef sendmsg_methods[] = {
    {"send1msg", (PyCFunction) sendmsg_sendmsg, METH_VARARGS | METH_KEYWORDS,
     sendmsg_sendmsg_doc},
    {"recv1msg", (PyCFunction) sendmsg_recvmsg, METH_VARARGS | METH_KEYWORDS,
     sendmsg_recvmsg_doc},
    {"getsockfam", (PyCFunction) sendmsg_getsockfam,
     METH_VARARGS | METH_KEYWORDS, sendmsg_getsockfam_doc},
    {NULL, NULL, 0, NULL}
};


PyMODINIT_FUNC init_sendmsg(void) {
    PyObject *module;

    sendmsg_socket_error = NULL; /* Make sure that this has a known value
                                    before doing anything that might exit. */

    module = Py_InitModule3("_sendmsg", sendmsg_methods, sendmsg_doc);

    if (!module) {
        return;
    }

    /*
      The following is the only value mentioned by POSIX:
      http://www.opengroup.org/onlinepubs/9699919799/basedefs/sys_socket.h.html
    */

    if (-1 == PyModule_AddIntConstant(module, "SCM_RIGHTS", SCM_RIGHTS)) {
        return;
    }


    /* BSD, Darwin, Hurd */
#if defined(SCM_CREDS)
    if (-1 == PyModule_AddIntConstant(module, "SCM_CREDS", SCM_CREDS)) {
        return;
    }
#endif

    /* Linux */
#if defined(SCM_CREDENTIALS)
    if (-1 == PyModule_AddIntConstant(module, "SCM_CREDENTIALS", SCM_CREDENTIALS)) {
        return;
    }
#endif

    /* Apparently everywhere, but not standardized. */
#if defined(SCM_TIMESTAMP)
    if (-1 == PyModule_AddIntConstant(module, "SCM_TIMESTAMP", SCM_TIMESTAMP)) {
        return;
    }
#endif

    module = PyImport_ImportModule("socket");
    if (!module) {
        return;
    }

    sendmsg_socket_error = PyObject_GetAttrString(module, "error");
    if (!sendmsg_socket_error) {
        return;
    }
}

static PyObject *sendmsg_sendmsg(PyObject *self, PyObject *args, PyObject *keywds) {

    int fd;
    int flags = 0;
    Py_ssize_t sendmsg_result, iovec_length;
    struct msghdr message_header;
    struct iovec iov[1];
    PyObject *ancillary = NULL;
    PyObject *iterator = NULL;
    PyObject *item = NULL;
    PyObject *result_object = NULL;

    static char *kwlist[] = {"fd", "data", "flags", "ancillary", NULL};

    if (!PyArg_ParseTupleAndKeywords(
            args, keywds, "it#|iO:sendmsg", kwlist,
            &fd,
            &iov[0].iov_base,
            &iovec_length,
            &flags,
            &ancillary)) {
        return NULL;
    }

    iov[0].iov_len = iovec_length;

    message_header.msg_name = NULL;
    message_header.msg_namelen = 0;

    message_header.msg_iov = iov;
    message_header.msg_iovlen = 1;

    message_header.msg_control = NULL;
    message_header.msg_controllen = 0;

    message_header.msg_flags = 0;

    if (ancillary) {

        if (!PyList_Check(ancillary)) {
            PyErr_Format(PyExc_TypeError,
                         "send1msg argument 3 expected list, got %s",
                         ancillary->ob_type->tp_name);
            goto finished;
        }

        iterator = PyObject_GetIter(ancillary);

        if (iterator == NULL) {
            goto finished;
        }

        size_t all_data_len = 0;

        /* First we need to know how big the buffer needs to be in order to
           have enough space for all of the messages. */
        while ( (item = PyIter_Next(iterator)) ) {
            int type, level;
            Py_ssize_t data_len;
            size_t prev_all_data_len;
            char *data;

            if (!PyTuple_Check(item)) {
                PyErr_Format(PyExc_TypeError,
                             "send1msg argument 3 expected list of tuple, "
                             "got list containing %s",
                             item->ob_type->tp_name);
                goto finished;
            }

            if (!PyArg_ParseTuple(
                        item, "iit#:sendmsg ancillary data (level, type, data)",
                        &level, &type, &data, &data_len)) {
                goto finished;
            }

            prev_all_data_len = all_data_len;
            all_data_len += CMSG_SPACE(data_len);

            Py_DECREF(item);
            item = NULL;

            if (all_data_len < prev_all_data_len) {
                PyErr_Format(PyExc_OverflowError,
                             "Too much msg_control to fit in a size_t: %zu",
                             prev_all_data_len);
                goto finished;
            }
        }

        Py_DECREF(iterator);
        iterator = NULL;

        /* Allocate the buffer for all of the ancillary elements, if we have
         * any.  */
        if (all_data_len) {
            if (all_data_len > SOCKLEN_MAX) {
                PyErr_Format(PyExc_OverflowError,
                             "Too much msg_control to fit in a socklen_t: %zu",
                             all_data_len);
                goto finished;
            }
            message_header.msg_control = PyMem_Malloc(all_data_len);
            if (!message_header.msg_control) {
                PyErr_NoMemory();
                goto finished;
            }
        } else {
            message_header.msg_control = NULL;
        }
        message_header.msg_controllen = (socklen_t) all_data_len;

        iterator = PyObject_GetIter(ancillary); /* again */

        if (!iterator) {
            goto finished;
        }

        /* Unpack the tuples into the control message. */
        struct cmsghdr *control_message = CMSG_FIRSTHDR(&message_header);
        while ( (item = PyIter_Next(iterator)) ) {
            int type, level;
            Py_ssize_t data_len;
            size_t data_size;
            unsigned char *data, *cmsg_data;

            /* We explicitly allocated enough space for all ancillary data
               above; if there isn't enough room, all bets are off. */
            assert(control_message);

            if (!PyArg_ParseTuple(item,
                                  "iit#:sendmsg ancillary data (level, type, data)",
                                  &level,
                                  &type,
                                  &data,
                                  &data_len)) {
                goto finished;
            }

            control_message->cmsg_level = level;
            control_message->cmsg_type = type;
            data_size = CMSG_LEN(data_len);

            if (data_size > SOCKLEN_MAX) {
                PyErr_Format(PyExc_OverflowError,
                             "CMSG_LEN(%zd) > SOCKLEN_MAX", data_len);
                goto finished;
            }

            control_message->cmsg_len = (socklen_t) data_size;

            cmsg_data = CMSG_DATA(control_message);
            memcpy(cmsg_data, data, data_len);

            Py_DECREF(item);
            item = NULL;

            control_message = CMSG_NXTHDR(&message_header, control_message);
        }
        Py_DECREF(iterator);
        iterator = NULL;

        if (PyErr_Occurred()) {
            goto finished;
        }
    }

    sendmsg_result = sendmsg(fd, &message_header, flags);

    if (sendmsg_result < 0) {
        PyErr_SetFromErrno(sendmsg_socket_error);
        goto finished;
    }

    result_object = Py_BuildValue("n", sendmsg_result);

 finished:

    if (item) {
        Py_DECREF(item);
        item = NULL;
    }
    if (iterator) {
        Py_DECREF(iterator);
        iterator = NULL;
    }
    if (message_header.msg_control) {
        PyMem_Free(message_header.msg_control);
        message_header.msg_control = NULL;
    }
    return result_object;
}

static PyObject *sendmsg_recvmsg(PyObject *self, PyObject *args, PyObject *keywds) {
    int fd = -1;
    int flags = 0;
    int maxsize = 8192;
    int cmsg_size = 4096;
    size_t cmsg_space;
    size_t cmsg_overhead;
    Py_ssize_t recvmsg_result;

    struct msghdr message_header;
    struct cmsghdr *control_message;
    struct iovec iov[1];
    char *cmsgbuf;
    PyObject *ancillary;
    PyObject *final_result = NULL;

    static char *kwlist[] = {"fd", "flags", "maxsize", "cmsg_size", NULL};

    if (!PyArg_ParseTupleAndKeywords(args, keywds, "i|iii:recvmsg", kwlist,
                                     &fd, &flags, &maxsize, &cmsg_size)) {
        return NULL;
    }

    cmsg_space = CMSG_SPACE(cmsg_size);

    /* overflow check */
    if (cmsg_space > SOCKLEN_MAX) {
        PyErr_Format(PyExc_OverflowError,
                     "CMSG_SPACE(cmsg_size) greater than SOCKLEN_MAX: %d",
                     cmsg_size);
        return NULL;
    }

    message_header.msg_name = NULL;
    message_header.msg_namelen = 0;

    iov[0].iov_len = maxsize;
    iov[0].iov_base = PyMem_Malloc(maxsize);

    if (!iov[0].iov_base) {
        PyErr_NoMemory();
        return NULL;
    }

    message_header.msg_iov = iov;
    message_header.msg_iovlen = 1;

    cmsgbuf = PyMem_Malloc(cmsg_space);

    if (!cmsgbuf) {
        PyMem_Free(iov[0].iov_base);
        PyErr_NoMemory();
        return NULL;
    }

    memset(cmsgbuf, 0, cmsg_space);
    message_header.msg_control = cmsgbuf;
    /* see above for overflow check */
    message_header.msg_controllen = (socklen_t) cmsg_space;

    recvmsg_result = recvmsg(fd, &message_header, flags);
    if (recvmsg_result < 0) {
        PyErr_SetFromErrno(sendmsg_socket_error);
        goto finished;
    }

    ancillary = PyList_New(0);
    if (!ancillary) {
        goto finished;
    }

    for (control_message = CMSG_FIRSTHDR(&message_header);
         control_message;
         control_message = CMSG_NXTHDR(&message_header,
                                       control_message)) {
        PyObject *entry;

        /* Some platforms apparently always fill out the ancillary data
           structure with a single bogus value if none is provided; ignore it,
           if that is the case. */

        if ((!(control_message->cmsg_level)) &&
            (!(control_message->cmsg_type))) {
            continue;
        }

        /*
         * Figure out how much of the cmsg size is cmsg structure overhead - in
         * other words, how much is not part of the application data.  This lets
         * us compute the right application data size below.  There should
         * really be a CMSG_ macro for this.
         */
        cmsg_overhead = (char*)CMSG_DATA(control_message) - (char*)control_message;

        entry = Py_BuildValue(
            "(iis#)",
            control_message->cmsg_level,
            control_message->cmsg_type,
            CMSG_DATA(control_message),
            (Py_ssize_t) (control_message->cmsg_len - cmsg_overhead));

        if (!entry) {
            Py_DECREF(ancillary);
            goto finished;
        }

        if (PyList_Append(ancillary, entry) < 0) {
            Py_DECREF(ancillary);
            Py_DECREF(entry);
            goto finished;
        } else {
            Py_DECREF(entry);
        }
    }

    final_result = Py_BuildValue(
        "s#iO",
        iov[0].iov_base,
        recvmsg_result,
        message_header.msg_flags,
        ancillary);

    Py_DECREF(ancillary);

  finished:
    PyMem_Free(iov[0].iov_base);
    PyMem_Free(cmsgbuf);
    return final_result;
}

static PyObject *sendmsg_getsockfam(PyObject *self, PyObject *args,
                                    PyObject *keywds) {
    int fd;
    struct sockaddr sa;
    static char *kwlist[] = {"fd", NULL};
    if (!PyArg_ParseTupleAndKeywords(args, keywds, "i", kwlist, &fd)) {
        return NULL;
    }
    socklen_t sz = sizeof(sa);
    if (getsockname(fd, &sa, &sz)) {
        PyErr_SetFromErrno(sendmsg_socket_error);
        return NULL;
    }
    return Py_BuildValue("i", sa.sa_family);
}
