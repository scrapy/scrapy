import socket
from sys import platform
from functools import wraps, partial
from itertools import count, chain
from weakref import WeakValueDictionary
from errno import errorcode

from six import binary_type as _binary_type
from six import integer_types as integer_types
from six import int2byte, indexbytes

from OpenSSL._util import (
    UNSPECIFIED as _UNSPECIFIED,
    exception_from_error_queue as _exception_from_error_queue,
    ffi as _ffi,
    lib as _lib,
    make_assert as _make_assert,
    native as _native,
    path_string as _path_string,
    text_to_bytes_and_warn as _text_to_bytes_and_warn,
)

from OpenSSL.crypto import (
    FILETYPE_PEM, _PassphraseHelper, PKey, X509Name, X509, X509Store)

try:
    _memoryview = memoryview
except NameError:
    class _memoryview(object):
        pass

try:
    _buffer = buffer
except NameError:
    class _buffer(object):
        pass

OPENSSL_VERSION_NUMBER = _lib.OPENSSL_VERSION_NUMBER
SSLEAY_VERSION = _lib.SSLEAY_VERSION
SSLEAY_CFLAGS = _lib.SSLEAY_CFLAGS
SSLEAY_PLATFORM = _lib.SSLEAY_PLATFORM
SSLEAY_DIR = _lib.SSLEAY_DIR
SSLEAY_BUILT_ON = _lib.SSLEAY_BUILT_ON

SENT_SHUTDOWN = _lib.SSL_SENT_SHUTDOWN
RECEIVED_SHUTDOWN = _lib.SSL_RECEIVED_SHUTDOWN

SSLv2_METHOD = 1
SSLv3_METHOD = 2
SSLv23_METHOD = 3
TLSv1_METHOD = 4
TLSv1_1_METHOD = 5
TLSv1_2_METHOD = 6

OP_NO_SSLv2 = _lib.SSL_OP_NO_SSLv2
OP_NO_SSLv3 = _lib.SSL_OP_NO_SSLv3
OP_NO_TLSv1 = _lib.SSL_OP_NO_TLSv1

OP_NO_TLSv1_1 = getattr(_lib, "SSL_OP_NO_TLSv1_1", 0)
OP_NO_TLSv1_2 = getattr(_lib, "SSL_OP_NO_TLSv1_2", 0)

MODE_RELEASE_BUFFERS = _lib.SSL_MODE_RELEASE_BUFFERS

OP_SINGLE_DH_USE = _lib.SSL_OP_SINGLE_DH_USE
OP_SINGLE_ECDH_USE = _lib.SSL_OP_SINGLE_ECDH_USE
OP_EPHEMERAL_RSA = _lib.SSL_OP_EPHEMERAL_RSA
OP_MICROSOFT_SESS_ID_BUG = _lib.SSL_OP_MICROSOFT_SESS_ID_BUG
OP_NETSCAPE_CHALLENGE_BUG = _lib.SSL_OP_NETSCAPE_CHALLENGE_BUG
OP_NETSCAPE_REUSE_CIPHER_CHANGE_BUG = (
    _lib.SSL_OP_NETSCAPE_REUSE_CIPHER_CHANGE_BUG
)
OP_SSLREF2_REUSE_CERT_TYPE_BUG = _lib.SSL_OP_SSLREF2_REUSE_CERT_TYPE_BUG
OP_MICROSOFT_BIG_SSLV3_BUFFER = _lib.SSL_OP_MICROSOFT_BIG_SSLV3_BUFFER
OP_MSIE_SSLV2_RSA_PADDING = _lib.SSL_OP_MSIE_SSLV2_RSA_PADDING
OP_SSLEAY_080_CLIENT_DH_BUG = _lib.SSL_OP_SSLEAY_080_CLIENT_DH_BUG
OP_TLS_D5_BUG = _lib.SSL_OP_TLS_D5_BUG
OP_TLS_BLOCK_PADDING_BUG = _lib.SSL_OP_TLS_BLOCK_PADDING_BUG
OP_DONT_INSERT_EMPTY_FRAGMENTS = _lib.SSL_OP_DONT_INSERT_EMPTY_FRAGMENTS
OP_CIPHER_SERVER_PREFERENCE = _lib.SSL_OP_CIPHER_SERVER_PREFERENCE
OP_TLS_ROLLBACK_BUG = _lib.SSL_OP_TLS_ROLLBACK_BUG
OP_PKCS1_CHECK_1 = _lib.SSL_OP_PKCS1_CHECK_1
OP_PKCS1_CHECK_2 = _lib.SSL_OP_PKCS1_CHECK_2
OP_NETSCAPE_CA_DN_BUG = _lib.SSL_OP_NETSCAPE_CA_DN_BUG
OP_NETSCAPE_DEMO_CIPHER_CHANGE_BUG = (
    _lib.SSL_OP_NETSCAPE_DEMO_CIPHER_CHANGE_BUG
)
OP_NO_COMPRESSION = _lib.SSL_OP_NO_COMPRESSION

OP_NO_QUERY_MTU = _lib.SSL_OP_NO_QUERY_MTU
OP_COOKIE_EXCHANGE = _lib.SSL_OP_COOKIE_EXCHANGE
OP_NO_TICKET = _lib.SSL_OP_NO_TICKET

OP_ALL = _lib.SSL_OP_ALL

VERIFY_PEER = _lib.SSL_VERIFY_PEER
VERIFY_FAIL_IF_NO_PEER_CERT = _lib.SSL_VERIFY_FAIL_IF_NO_PEER_CERT
VERIFY_CLIENT_ONCE = _lib.SSL_VERIFY_CLIENT_ONCE
VERIFY_NONE = _lib.SSL_VERIFY_NONE

SESS_CACHE_OFF = _lib.SSL_SESS_CACHE_OFF
SESS_CACHE_CLIENT = _lib.SSL_SESS_CACHE_CLIENT
SESS_CACHE_SERVER = _lib.SSL_SESS_CACHE_SERVER
SESS_CACHE_BOTH = _lib.SSL_SESS_CACHE_BOTH
SESS_CACHE_NO_AUTO_CLEAR = _lib.SSL_SESS_CACHE_NO_AUTO_CLEAR
SESS_CACHE_NO_INTERNAL_LOOKUP = _lib.SSL_SESS_CACHE_NO_INTERNAL_LOOKUP
SESS_CACHE_NO_INTERNAL_STORE = _lib.SSL_SESS_CACHE_NO_INTERNAL_STORE
SESS_CACHE_NO_INTERNAL = _lib.SSL_SESS_CACHE_NO_INTERNAL

SSL_ST_CONNECT = _lib.SSL_ST_CONNECT
SSL_ST_ACCEPT = _lib.SSL_ST_ACCEPT
SSL_ST_MASK = _lib.SSL_ST_MASK
if _lib.Cryptography_HAS_SSL_ST:
    SSL_ST_INIT = _lib.SSL_ST_INIT
    SSL_ST_BEFORE = _lib.SSL_ST_BEFORE
    SSL_ST_OK = _lib.SSL_ST_OK
    SSL_ST_RENEGOTIATE = _lib.SSL_ST_RENEGOTIATE

SSL_CB_LOOP = _lib.SSL_CB_LOOP
SSL_CB_EXIT = _lib.SSL_CB_EXIT
SSL_CB_READ = _lib.SSL_CB_READ
SSL_CB_WRITE = _lib.SSL_CB_WRITE
SSL_CB_ALERT = _lib.SSL_CB_ALERT
SSL_CB_READ_ALERT = _lib.SSL_CB_READ_ALERT
SSL_CB_WRITE_ALERT = _lib.SSL_CB_WRITE_ALERT
SSL_CB_ACCEPT_LOOP = _lib.SSL_CB_ACCEPT_LOOP
SSL_CB_ACCEPT_EXIT = _lib.SSL_CB_ACCEPT_EXIT
SSL_CB_CONNECT_LOOP = _lib.SSL_CB_CONNECT_LOOP
SSL_CB_CONNECT_EXIT = _lib.SSL_CB_CONNECT_EXIT
SSL_CB_HANDSHAKE_START = _lib.SSL_CB_HANDSHAKE_START
SSL_CB_HANDSHAKE_DONE = _lib.SSL_CB_HANDSHAKE_DONE


class Error(Exception):
    """
    An error occurred in an `OpenSSL.SSL` API.
    """


_raise_current_error = partial(_exception_from_error_queue, Error)
_openssl_assert = _make_assert(Error)


class WantReadError(Error):
    pass


class WantWriteError(Error):
    pass


class WantX509LookupError(Error):
    pass


class ZeroReturnError(Error):
    pass


class SysCallError(Error):
    pass


class _CallbackExceptionHelper(object):
    """
    A base class for wrapper classes that allow for intelligent exception
    handling in OpenSSL callbacks.

    :ivar list _problems: Any exceptions that occurred while executing in a
        context where they could not be raised in the normal way.  Typically
        this is because OpenSSL has called into some Python code and requires a
        return value.  The exceptions are saved to be raised later when it is
        possible to do so.
    """

    def __init__(self):
        self._problems = []

    def raise_if_problem(self):
        """
        Raise an exception from the OpenSSL error queue or that was previously
        captured whe running a callback.
        """
        if self._problems:
            try:
                _raise_current_error()
            except Error:
                pass
            raise self._problems.pop(0)


class _VerifyHelper(_CallbackExceptionHelper):
    """
    Wrap a callback such that it can be used as a certificate verification
    callback.
    """

    def __init__(self, callback):
        _CallbackExceptionHelper.__init__(self)

        @wraps(callback)
        def wrapper(ok, store_ctx):
            cert = X509.__new__(X509)
            cert._x509 = _lib.X509_STORE_CTX_get_current_cert(store_ctx)
            error_number = _lib.X509_STORE_CTX_get_error(store_ctx)
            error_depth = _lib.X509_STORE_CTX_get_error_depth(store_ctx)

            index = _lib.SSL_get_ex_data_X509_STORE_CTX_idx()
            ssl = _lib.X509_STORE_CTX_get_ex_data(store_ctx, index)
            connection = Connection._reverse_mapping[ssl]

            try:
                result = callback(
                    connection, cert, error_number, error_depth, ok
                )
            except Exception as e:
                self._problems.append(e)
                return 0
            else:
                if result:
                    _lib.X509_STORE_CTX_set_error(store_ctx, _lib.X509_V_OK)
                    return 1
                else:
                    return 0

        self.callback = _ffi.callback(
            "int (*)(int, X509_STORE_CTX *)", wrapper)


class _NpnAdvertiseHelper(_CallbackExceptionHelper):
    """
    Wrap a callback such that it can be used as an NPN advertisement callback.
    """

    def __init__(self, callback):
        _CallbackExceptionHelper.__init__(self)

        @wraps(callback)
        def wrapper(ssl, out, outlen, arg):
            try:
                conn = Connection._reverse_mapping[ssl]
                protos = callback(conn)

                # Join the protocols into a Python bytestring, length-prefixing
                # each element.
                protostr = b''.join(
                    chain.from_iterable((int2byte(len(p)), p) for p in protos)
                )

                # Save our callback arguments on the connection object. This is
                # done to make sure that they don't get freed before OpenSSL
                # uses them. Then, return them appropriately in the output
                # parameters.
                conn._npn_advertise_callback_args = [
                    _ffi.new("unsigned int *", len(protostr)),
                    _ffi.new("unsigned char[]", protostr),
                ]
                outlen[0] = conn._npn_advertise_callback_args[0][0]
                out[0] = conn._npn_advertise_callback_args[1]
                return 0
            except Exception as e:
                self._problems.append(e)
                return 2  # SSL_TLSEXT_ERR_ALERT_FATAL

        self.callback = _ffi.callback(
            "int (*)(SSL *, const unsigned char **, unsigned int *, void *)",
            wrapper
        )


class _NpnSelectHelper(_CallbackExceptionHelper):
    """
    Wrap a callback such that it can be used as an NPN selection callback.
    """

    def __init__(self, callback):
        _CallbackExceptionHelper.__init__(self)

        @wraps(callback)
        def wrapper(ssl, out, outlen, in_, inlen, arg):
            try:
                conn = Connection._reverse_mapping[ssl]

                # The string passed to us is actually made up of multiple
                # length-prefixed bytestrings. We need to split that into a
                # list.
                instr = _ffi.buffer(in_, inlen)[:]
                protolist = []
                while instr:
                    l = indexbytes(instr, 0)
                    proto = instr[1:l + 1]
                    protolist.append(proto)
                    instr = instr[l + 1:]

                # Call the callback
                outstr = callback(conn, protolist)

                # Save our callback arguments on the connection object. This is
                # done to make sure that they don't get freed before OpenSSL
                # uses them. Then, return them appropriately in the output
                # parameters.
                conn._npn_select_callback_args = [
                    _ffi.new("unsigned char *", len(outstr)),
                    _ffi.new("unsigned char[]", outstr),
                ]
                outlen[0] = conn._npn_select_callback_args[0][0]
                out[0] = conn._npn_select_callback_args[1]
                return 0
            except Exception as e:
                self._problems.append(e)
                return 2  # SSL_TLSEXT_ERR_ALERT_FATAL

        self.callback = _ffi.callback(
            ("int (*)(SSL *, unsigned char **, unsigned char *, "
                "const unsigned char *, unsigned int, void *)"),
            wrapper
        )


class _ALPNSelectHelper(_CallbackExceptionHelper):
    """
    Wrap a callback such that it can be used as an ALPN selection callback.
    """

    def __init__(self, callback):
        _CallbackExceptionHelper.__init__(self)

        @wraps(callback)
        def wrapper(ssl, out, outlen, in_, inlen, arg):
            try:
                conn = Connection._reverse_mapping[ssl]

                # The string passed to us is made up of multiple
                # length-prefixed bytestrings. We need to split that into a
                # list.
                instr = _ffi.buffer(in_, inlen)[:]
                protolist = []
                while instr:
                    encoded_len = indexbytes(instr, 0)
                    proto = instr[1:encoded_len + 1]
                    protolist.append(proto)
                    instr = instr[encoded_len + 1:]

                # Call the callback
                outstr = callback(conn, protolist)

                if not isinstance(outstr, _binary_type):
                    raise TypeError("ALPN callback must return a bytestring.")

                # Save our callback arguments on the connection object to make
                # sure that they don't get freed before OpenSSL can use them.
                # Then, return them in the appropriate output parameters.
                conn._alpn_select_callback_args = [
                    _ffi.new("unsigned char *", len(outstr)),
                    _ffi.new("unsigned char[]", outstr),
                ]
                outlen[0] = conn._alpn_select_callback_args[0][0]
                out[0] = conn._alpn_select_callback_args[1]
                return 0
            except Exception as e:
                self._problems.append(e)
                return 2  # SSL_TLSEXT_ERR_ALERT_FATAL

        self.callback = _ffi.callback(
            ("int (*)(SSL *, unsigned char **, unsigned char *, "
                "const unsigned char *, unsigned int, void *)"),
            wrapper
        )


def _asFileDescriptor(obj):
    fd = None
    if not isinstance(obj, integer_types):
        meth = getattr(obj, "fileno", None)
        if meth is not None:
            obj = meth()

    if isinstance(obj, integer_types):
        fd = obj

    if not isinstance(fd, integer_types):
        raise TypeError("argument must be an int, or have a fileno() method.")
    elif fd < 0:
        raise ValueError(
            "file descriptor cannot be a negative integer (%i)" % (fd,))

    return fd


def SSLeay_version(type):
    """
    Return a string describing the version of OpenSSL in use.

    :param type: One of the SSLEAY_ constants defined in this module.
    """
    return _ffi.string(_lib.SSLeay_version(type))


def _make_requires(flag, error):
    """
    Builds a decorator that ensures that functions that rely on OpenSSL
    functions that are not present in this build raise NotImplementedError,
    rather than AttributeError coming out of cryptography.

    :param flag: A cryptography flag that guards the functions, e.g.
        ``Cryptography_HAS_NEXTPROTONEG``.
    :param error: The string to be used in the exception if the flag is false.
    """
    def _requires_decorator(func):
        if not flag:
            @wraps(func)
            def explode(*args, **kwargs):
                raise NotImplementedError(error)
            return explode
        else:
            return func

    return _requires_decorator


_requires_npn = _make_requires(
    _lib.Cryptography_HAS_NEXTPROTONEG, "NPN not available"
)


_requires_alpn = _make_requires(
    _lib.Cryptography_HAS_ALPN, "ALPN not available"
)


_requires_sni = _make_requires(
    _lib.Cryptography_HAS_TLSEXT_HOSTNAME, "SNI not available"
)


class Session(object):
    pass


class Context(object):
    """
    :class:`OpenSSL.SSL.Context` instances define the parameters for setting
    up new SSL connections.
    """
    _methods = {
        SSLv2_METHOD: "SSLv2_method",
        SSLv3_METHOD: "SSLv3_method",
        SSLv23_METHOD: "SSLv23_method",
        TLSv1_METHOD: "TLSv1_method",
        TLSv1_1_METHOD: "TLSv1_1_method",
        TLSv1_2_METHOD: "TLSv1_2_method",
    }
    _methods = dict(
        (identifier, getattr(_lib, name))
        for (identifier, name) in _methods.items()
        if getattr(_lib, name, None) is not None)

    def __init__(self, method):
        """
        :param method: One of SSLv2_METHOD, SSLv3_METHOD, SSLv23_METHOD, or
            TLSv1_METHOD.
        """
        if not isinstance(method, integer_types):
            raise TypeError("method must be an integer")

        try:
            method_func = self._methods[method]
        except KeyError:
            raise ValueError("No such protocol")

        method_obj = method_func()
        _openssl_assert(method_obj != _ffi.NULL)

        context = _lib.SSL_CTX_new(method_obj)
        _openssl_assert(context != _ffi.NULL)
        context = _ffi.gc(context, _lib.SSL_CTX_free)

        self._context = context
        self._passphrase_helper = None
        self._passphrase_callback = None
        self._passphrase_userdata = None
        self._verify_helper = None
        self._verify_callback = None
        self._info_callback = None
        self._tlsext_servername_callback = None
        self._app_data = None
        self._npn_advertise_helper = None
        self._npn_advertise_callback = None
        self._npn_select_helper = None
        self._npn_select_callback = None
        self._alpn_select_helper = None
        self._alpn_select_callback = None

        # SSL_CTX_set_app_data(self->ctx, self);
        # SSL_CTX_set_mode(self->ctx, SSL_MODE_ENABLE_PARTIAL_WRITE |
        #                             SSL_MODE_ACCEPT_MOVING_WRITE_BUFFER |
        #                             SSL_MODE_AUTO_RETRY);
        self.set_mode(_lib.SSL_MODE_ENABLE_PARTIAL_WRITE)

    def load_verify_locations(self, cafile, capath=None):
        """
        Let SSL know where we can find trusted certificates for the certificate
        chain

        :param cafile: In which file we can find the certificates (``bytes`` or
            ``unicode``).
        :param capath: In which directory we can find the certificates
            (``bytes`` or ``unicode``).

        :return: None
        """
        if cafile is None:
            cafile = _ffi.NULL
        else:
            cafile = _path_string(cafile)

        if capath is None:
            capath = _ffi.NULL
        else:
            capath = _path_string(capath)

        load_result = _lib.SSL_CTX_load_verify_locations(
            self._context, cafile, capath
        )
        if not load_result:
            _raise_current_error()

    def _wrap_callback(self, callback):
        @wraps(callback)
        def wrapper(size, verify, userdata):
            return callback(size, verify, self._passphrase_userdata)
        return _PassphraseHelper(
            FILETYPE_PEM, wrapper, more_args=True, truncate=True)

    def set_passwd_cb(self, callback, userdata=None):
        """
        Set the passphrase callback

        :param callback: The Python callback to use
        :param userdata: (optional) A Python object which will be given as
                         argument to the callback
        :return: None
        """
        if not callable(callback):
            raise TypeError("callback must be callable")

        self._passphrase_helper = self._wrap_callback(callback)
        self._passphrase_callback = self._passphrase_helper.callback
        _lib.SSL_CTX_set_default_passwd_cb(
            self._context, self._passphrase_callback)
        self._passphrase_userdata = userdata

    def set_default_verify_paths(self):
        """
        Use the platform-specific CA certificate locations

        :return: None
        """
        set_result = _lib.SSL_CTX_set_default_verify_paths(self._context)
        _openssl_assert(set_result == 1)

    def use_certificate_chain_file(self, certfile):
        """
        Load a certificate chain from a file

        :param certfile: The name of the certificate chain file (``bytes`` or
            ``unicode``).

        :return: None
        """
        certfile = _path_string(certfile)

        result = _lib.SSL_CTX_use_certificate_chain_file(
            self._context, certfile
        )
        if not result:
            _raise_current_error()

    def use_certificate_file(self, certfile, filetype=FILETYPE_PEM):
        """
        Load a certificate from a file

        :param certfile: The name of the certificate file (``bytes`` or
            ``unicode``).
        :param filetype: (optional) The encoding of the file, default is PEM

        :return: None
        """
        certfile = _path_string(certfile)
        if not isinstance(filetype, integer_types):
            raise TypeError("filetype must be an integer")

        use_result = _lib.SSL_CTX_use_certificate_file(
            self._context, certfile, filetype
        )
        if not use_result:
            _raise_current_error()

    def use_certificate(self, cert):
        """
        Load a certificate from a X509 object

        :param cert: The X509 object
        :return: None
        """
        if not isinstance(cert, X509):
            raise TypeError("cert must be an X509 instance")

        use_result = _lib.SSL_CTX_use_certificate(self._context, cert._x509)
        if not use_result:
            _raise_current_error()

    def add_extra_chain_cert(self, certobj):
        """
        Add certificate to chain

        :param certobj: The X509 certificate object to add to the chain
        :return: None
        """
        if not isinstance(certobj, X509):
            raise TypeError("certobj must be an X509 instance")

        copy = _lib.X509_dup(certobj._x509)
        add_result = _lib.SSL_CTX_add_extra_chain_cert(self._context, copy)
        if not add_result:
            # TODO: This is untested.
            _lib.X509_free(copy)
            _raise_current_error()

    def _raise_passphrase_exception(self):
        if self._passphrase_helper is None:
            _raise_current_error()
        exception = self._passphrase_helper.raise_if_problem(Error)
        if exception is not None:
            raise exception

    def use_privatekey_file(self, keyfile, filetype=_UNSPECIFIED):
        """
        Load a private key from a file

        :param keyfile: The name of the key file (``bytes`` or ``unicode``)
        :param filetype: (optional) The encoding of the file, default is PEM

        :return: None
        """
        keyfile = _path_string(keyfile)

        if filetype is _UNSPECIFIED:
            filetype = FILETYPE_PEM
        elif not isinstance(filetype, integer_types):
            raise TypeError("filetype must be an integer")

        use_result = _lib.SSL_CTX_use_PrivateKey_file(
            self._context, keyfile, filetype)
        if not use_result:
            self._raise_passphrase_exception()

    def use_privatekey(self, pkey):
        """
        Load a private key from a PKey object

        :param pkey: The PKey object
        :return: None
        """
        if not isinstance(pkey, PKey):
            raise TypeError("pkey must be a PKey instance")

        use_result = _lib.SSL_CTX_use_PrivateKey(self._context, pkey._pkey)
        if not use_result:
            self._raise_passphrase_exception()

    def check_privatekey(self):
        """
        Check that the private key and certificate match up

        :return: None (raises an exception if something's wrong)
        """
        if not _lib.SSL_CTX_check_private_key(self._context):
            _raise_current_error()

    def load_client_ca(self, cafile):
        """
        Load the trusted certificates that will be sent to the client.  Does
        not actually imply any of the certificates are trusted; that must be
        configured separately.

        :param bytes cafile: The path to a certificates file in PEM format.
        :return: None
        """
        ca_list = _lib.SSL_load_client_CA_file(
            _text_to_bytes_and_warn("cafile", cafile)
        )
        _openssl_assert(ca_list != _ffi.NULL)
        # SSL_CTX_set_client_CA_list doesn't return anything.
        _lib.SSL_CTX_set_client_CA_list(self._context, ca_list)

    def set_session_id(self, buf):
        """
        Set the session id to *buf* within which a session can be reused for
        this Context object.  This is needed when doing session resumption,
        because there is no way for a stored session to know which Context
        object it is associated with.

        :param bytes buf: The session id.

        :returns: None
        """
        buf = _text_to_bytes_and_warn("buf", buf)
        _openssl_assert(
            _lib.SSL_CTX_set_session_id_context(
                self._context,
                buf,
                len(buf),
            ) == 1
        )

    def set_session_cache_mode(self, mode):
        """
        Enable/disable session caching and specify the mode used.

        :param mode: One or more of the SESS_CACHE_* flags (combine using
            bitwise or)
        :returns: The previously set caching mode.
        """
        if not isinstance(mode, integer_types):
            raise TypeError("mode must be an integer")

        return _lib.SSL_CTX_set_session_cache_mode(self._context, mode)

    def get_session_cache_mode(self):
        """
        :returns: The currently used cache mode.
        """
        return _lib.SSL_CTX_get_session_cache_mode(self._context)

    def set_verify(self, mode, callback):
        """
        Set the verify mode and verify callback

        :param mode: The verify mode, this is either VERIFY_NONE or
                     VERIFY_PEER combined with possible other flags
        :param callback: The Python callback to use
        :return: None

        See SSL_CTX_set_verify(3SSL) for further details.
        """
        if not isinstance(mode, integer_types):
            raise TypeError("mode must be an integer")

        if not callable(callback):
            raise TypeError("callback must be callable")

        self._verify_helper = _VerifyHelper(callback)
        self._verify_callback = self._verify_helper.callback
        _lib.SSL_CTX_set_verify(self._context, mode, self._verify_callback)

    def set_verify_depth(self, depth):
        """
        Set the verify depth

        :param depth: An integer specifying the verify depth
        :return: None
        """
        if not isinstance(depth, integer_types):
            raise TypeError("depth must be an integer")

        _lib.SSL_CTX_set_verify_depth(self._context, depth)

    def get_verify_mode(self):
        """
        Get the verify mode

        :return: The verify mode
        """
        return _lib.SSL_CTX_get_verify_mode(self._context)

    def get_verify_depth(self):
        """
        Get the verify depth

        :return: The verify depth
        """
        return _lib.SSL_CTX_get_verify_depth(self._context)

    def load_tmp_dh(self, dhfile):
        """
        Load parameters for Ephemeral Diffie-Hellman

        :param dhfile: The file to load EDH parameters from (``bytes`` or
            ``unicode``).

        :return: None
        """
        dhfile = _path_string(dhfile)

        bio = _lib.BIO_new_file(dhfile, b"r")
        if bio == _ffi.NULL:
            _raise_current_error()
        bio = _ffi.gc(bio, _lib.BIO_free)

        dh = _lib.PEM_read_bio_DHparams(bio, _ffi.NULL, _ffi.NULL, _ffi.NULL)
        dh = _ffi.gc(dh, _lib.DH_free)
        _lib.SSL_CTX_set_tmp_dh(self._context, dh)

    def set_tmp_ecdh(self, curve):
        """
        Select a curve to use for ECDHE key exchange.

        :param curve: A curve object to use as returned by either
            :py:meth:`OpenSSL.crypto.get_elliptic_curve` or
            :py:meth:`OpenSSL.crypto.get_elliptic_curves`.

        :return: None
        """
        _lib.SSL_CTX_set_tmp_ecdh(self._context, curve._to_EC_KEY())

    def set_cipher_list(self, cipher_list):
        """
        Set the list of ciphers to be used in this context.

        See the OpenSSL manual for more information (e.g.
        :manpage:`ciphers(1)`).

        :param bytes cipher_list: An OpenSSL cipher string.
        :return: None
        """
        cipher_list = _text_to_bytes_and_warn("cipher_list", cipher_list)

        if not isinstance(cipher_list, bytes):
            raise TypeError("cipher_list must be a byte string.")

        _openssl_assert(
            _lib.SSL_CTX_set_cipher_list(self._context, cipher_list) == 1
        )

    def set_client_ca_list(self, certificate_authorities):
        """
        Set the list of preferred client certificate signers for this server
        context.

        This list of certificate authorities will be sent to the client when
        the server requests a client certificate.

        :param certificate_authorities: a sequence of X509Names.
        :return: None
        """
        name_stack = _lib.sk_X509_NAME_new_null()
        _openssl_assert(name_stack != _ffi.NULL)

        try:
            for ca_name in certificate_authorities:
                if not isinstance(ca_name, X509Name):
                    raise TypeError(
                        "client CAs must be X509Name objects, not %s "
                        "objects" % (
                            type(ca_name).__name__,
                        )
                    )
                copy = _lib.X509_NAME_dup(ca_name._name)
                _openssl_assert(copy != _ffi.NULL)
                push_result = _lib.sk_X509_NAME_push(name_stack, copy)
                if not push_result:
                    _lib.X509_NAME_free(copy)
                    _raise_current_error()
        except:
            _lib.sk_X509_NAME_free(name_stack)
            raise

        _lib.SSL_CTX_set_client_CA_list(self._context, name_stack)

    def add_client_ca(self, certificate_authority):
        """
        Add the CA certificate to the list of preferred signers for this
        context.

        The list of certificate authorities will be sent to the client when the
        server requests a client certificate.

        :param certificate_authority: certificate authority's X509 certificate.
        :return: None
        """
        if not isinstance(certificate_authority, X509):
            raise TypeError("certificate_authority must be an X509 instance")

        add_result = _lib.SSL_CTX_add_client_CA(
            self._context, certificate_authority._x509)
        _openssl_assert(add_result == 1)

    def set_timeout(self, timeout):
        """
        Set session timeout

        :param timeout: The timeout in seconds
        :return: The previous session timeout
        """
        if not isinstance(timeout, integer_types):
            raise TypeError("timeout must be an integer")

        return _lib.SSL_CTX_set_timeout(self._context, timeout)

    def get_timeout(self):
        """
        Get the session timeout

        :return: The session timeout
        """
        return _lib.SSL_CTX_get_timeout(self._context)

    def set_info_callback(self, callback):
        """
        Set the info callback

        :param callback: The Python callback to use
        :return: None
        """
        @wraps(callback)
        def wrapper(ssl, where, return_code):
            callback(Connection._reverse_mapping[ssl], where, return_code)
        self._info_callback = _ffi.callback(
            "void (*)(const SSL *, int, int)", wrapper)
        _lib.SSL_CTX_set_info_callback(self._context, self._info_callback)

    def get_app_data(self):
        """
        Get the application data (supplied via set_app_data())

        :return: The application data
        """
        return self._app_data

    def set_app_data(self, data):
        """
        Set the application data (will be returned from get_app_data())

        :param data: Any Python object
        :return: None
        """
        self._app_data = data

    def get_cert_store(self):
        """
        Get the certificate store for the context.

        :return: A X509Store object or None if it does not have one.
        """
        store = _lib.SSL_CTX_get_cert_store(self._context)
        if store == _ffi.NULL:
            # TODO: This is untested.
            return None

        pystore = X509Store.__new__(X509Store)
        pystore._store = store
        return pystore

    def set_options(self, options):
        """
        Add options. Options set before are not cleared!

        :param options: The options to add.
        :return: The new option bitmask.
        """
        if not isinstance(options, integer_types):
            raise TypeError("options must be an integer")

        return _lib.SSL_CTX_set_options(self._context, options)

    def set_mode(self, mode):
        """
        Add modes via bitmask. Modes set before are not cleared!

        :param mode: The mode to add.
        :return: The new mode bitmask.
        """
        if not isinstance(mode, integer_types):
            raise TypeError("mode must be an integer")

        return _lib.SSL_CTX_set_mode(self._context, mode)

    @_requires_sni
    def set_tlsext_servername_callback(self, callback):
        """
        Specify a callback function to be called when clients specify a server
        name.

        :param callback: The callback function.  It will be invoked with one
            argument, the Connection instance.
        """
        @wraps(callback)
        def wrapper(ssl, alert, arg):
            callback(Connection._reverse_mapping[ssl])
            return 0

        self._tlsext_servername_callback = _ffi.callback(
            "int (*)(const SSL *, int *, void *)", wrapper)
        _lib.SSL_CTX_set_tlsext_servername_callback(
            self._context, self._tlsext_servername_callback)

    @_requires_npn
    def set_npn_advertise_callback(self, callback):
        """
        Specify a callback function that will be called when offering `Next
        Protocol Negotiation
        <https://technotes.googlecode.com/git/nextprotoneg.html>`_ as a server.

        :param callback: The callback function.  It will be invoked with one
            argument, the Connection instance.  It should return a list of
            bytestrings representing the advertised protocols, like
            ``[b'http/1.1', b'spdy/2']``.
        """
        self._npn_advertise_helper = _NpnAdvertiseHelper(callback)
        self._npn_advertise_callback = self._npn_advertise_helper.callback
        _lib.SSL_CTX_set_next_protos_advertised_cb(
            self._context, self._npn_advertise_callback, _ffi.NULL)

    @_requires_npn
    def set_npn_select_callback(self, callback):
        """
        Specify a callback function that will be called when a server offers
        Next Protocol Negotiation options.

        :param callback: The callback function.  It will be invoked with two
            arguments: the Connection, and a list of offered protocols as
            bytestrings, e.g. ``[b'http/1.1', b'spdy/2']``.  It should return
            one of those bytestrings, the chosen protocol.
        """
        self._npn_select_helper = _NpnSelectHelper(callback)
        self._npn_select_callback = self._npn_select_helper.callback
        _lib.SSL_CTX_set_next_proto_select_cb(
            self._context, self._npn_select_callback, _ffi.NULL)

    @_requires_alpn
    def set_alpn_protos(self, protos):
        """
        Specify the clients ALPN protocol list.

        These protocols are offered to the server during protocol negotiation.

        :param protos: A list of the protocols to be offered to the server.
            This list should be a Python list of bytestrings representing the
            protocols to offer, e.g. ``[b'http/1.1', b'spdy/2']``.
        """
        # Take the list of protocols and join them together, prefixing them
        # with their lengths.
        protostr = b''.join(
            chain.from_iterable((int2byte(len(p)), p) for p in protos)
        )

        # Build a C string from the list. We don't need to save this off
        # because OpenSSL immediately copies the data out.
        input_str = _ffi.new("unsigned char[]", protostr)
        input_str_len = _ffi.cast("unsigned", len(protostr))
        _lib.SSL_CTX_set_alpn_protos(self._context, input_str, input_str_len)

    @_requires_alpn
    def set_alpn_select_callback(self, callback):
        """
        Set the callback to handle ALPN protocol choice.

        :param callback: The callback function.  It will be invoked with two
            arguments: the Connection, and a list of offered protocols as
            bytestrings, e.g ``[b'http/1.1', b'spdy/2']``.  It should return
            one of those bytestrings, the chosen protocol.
        """
        self._alpn_select_helper = _ALPNSelectHelper(callback)
        self._alpn_select_callback = self._alpn_select_helper.callback
        _lib.SSL_CTX_set_alpn_select_cb(
            self._context, self._alpn_select_callback, _ffi.NULL)

ContextType = Context


class Connection(object):
    """
    """
    _reverse_mapping = WeakValueDictionary()

    def __init__(self, context, socket=None):
        """
        Create a new Connection object, using the given OpenSSL.SSL.Context
        instance and socket.

        :param context: An SSL Context to use for this connection
        :param socket: The socket to use for transport layer
        """
        if not isinstance(context, Context):
            raise TypeError("context must be a Context instance")

        ssl = _lib.SSL_new(context._context)
        self._ssl = _ffi.gc(ssl, _lib.SSL_free)
        self._context = context
        self._app_data = None

        # References to strings used for Next Protocol Negotiation. OpenSSL's
        # header files suggest that these might get copied at some point, but
        # doesn't specify when, so we store them here to make sure they don't
        # get freed before OpenSSL uses them.
        self._npn_advertise_callback_args = None
        self._npn_select_callback_args = None

        # References to strings used for Application Layer Protocol
        # Negotiation. These strings get copied at some point but it's well
        # after the callback returns, so we have to hang them somewhere to
        # avoid them getting freed.
        self._alpn_select_callback_args = None

        self._reverse_mapping[self._ssl] = self

        if socket is None:
            self._socket = None
            # Don't set up any gc for these, SSL_free will take care of them.
            self._into_ssl = _lib.BIO_new(_lib.BIO_s_mem())
            _openssl_assert(self._into_ssl != _ffi.NULL)

            self._from_ssl = _lib.BIO_new(_lib.BIO_s_mem())
            _openssl_assert(self._from_ssl != _ffi.NULL)

            _lib.SSL_set_bio(self._ssl, self._into_ssl, self._from_ssl)
        else:
            self._into_ssl = None
            self._from_ssl = None
            self._socket = socket
            set_result = _lib.SSL_set_fd(
                self._ssl, _asFileDescriptor(self._socket))
            _openssl_assert(set_result == 1)

    def __getattr__(self, name):
        """
        Look up attributes on the wrapped socket object if they are not found
        on the Connection object.
        """
        if self._socket is None:
            raise AttributeError("'%s' object has no attribute '%s'" % (
                self.__class__.__name__, name
            ))
        else:
            return getattr(self._socket, name)

    def _raise_ssl_error(self, ssl, result):
        if self._context._verify_helper is not None:
            self._context._verify_helper.raise_if_problem()
        if self._context._npn_advertise_helper is not None:
            self._context._npn_advertise_helper.raise_if_problem()
        if self._context._npn_select_helper is not None:
            self._context._npn_select_helper.raise_if_problem()
        if self._context._alpn_select_helper is not None:
            self._context._alpn_select_helper.raise_if_problem()

        error = _lib.SSL_get_error(ssl, result)
        if error == _lib.SSL_ERROR_WANT_READ:
            raise WantReadError()
        elif error == _lib.SSL_ERROR_WANT_WRITE:
            raise WantWriteError()
        elif error == _lib.SSL_ERROR_ZERO_RETURN:
            raise ZeroReturnError()
        elif error == _lib.SSL_ERROR_WANT_X509_LOOKUP:
            # TODO: This is untested.
            raise WantX509LookupError()
        elif error == _lib.SSL_ERROR_SYSCALL:
            if _lib.ERR_peek_error() == 0:
                if result < 0:
                    if platform == "win32":
                        errno = _ffi.getwinerror()[0]
                    else:
                        errno = _ffi.errno

                    if errno != 0:
                        raise SysCallError(errno, errorcode.get(errno))
                raise SysCallError(-1, "Unexpected EOF")
            else:
                # TODO: This is untested.
                _raise_current_error()
        elif error == _lib.SSL_ERROR_NONE:
            pass
        else:
            _raise_current_error()

    def get_context(self):
        """
        Get session context
        """
        return self._context

    def set_context(self, context):
        """
        Switch this connection to a new session context

        :param context: A :py:class:`Context` instance giving the new session
            context to use.
        """
        if not isinstance(context, Context):
            raise TypeError("context must be a Context instance")

        _lib.SSL_set_SSL_CTX(self._ssl, context._context)
        self._context = context

    @_requires_sni
    def get_servername(self):
        """
        Retrieve the servername extension value if provided in the client hello
        message, or None if there wasn't one.

        :return: A byte string giving the server name or :py:data:`None`.
        """
        name = _lib.SSL_get_servername(
            self._ssl, _lib.TLSEXT_NAMETYPE_host_name
        )
        if name == _ffi.NULL:
            return None

        return _ffi.string(name)

    @_requires_sni
    def set_tlsext_host_name(self, name):
        """
        Set the value of the servername extension to send in the client hello.

        :param name: A byte string giving the name.
        """
        if not isinstance(name, bytes):
            raise TypeError("name must be a byte string")
        elif b"\0" in name:
            raise TypeError("name must not contain NUL byte")

        # XXX I guess this can fail sometimes?
        _lib.SSL_set_tlsext_host_name(self._ssl, name)

    def pending(self):
        """
        Get the number of bytes that can be safely read from the connection

        :return: The number of bytes available in the receive buffer.
        """
        return _lib.SSL_pending(self._ssl)

    def send(self, buf, flags=0):
        """
        Send data on the connection. NOTE: If you get one of the WantRead,
        WantWrite or WantX509Lookup exceptions on this, you have to call the
        method again with the SAME buffer.

        :param buf: The string, buffer or memoryview to send
        :param flags: (optional) Included for compatibility with the socket
                      API, the value is ignored
        :return: The number of bytes written
        """
        # Backward compatibility
        buf = _text_to_bytes_and_warn("buf", buf)

        if isinstance(buf, _memoryview):
            buf = buf.tobytes()
        if isinstance(buf, _buffer):
            buf = str(buf)
        if not isinstance(buf, bytes):
            raise TypeError("data must be a memoryview, buffer or byte string")

        result = _lib.SSL_write(self._ssl, buf, len(buf))
        self._raise_ssl_error(self._ssl, result)
        return result
    write = send

    def sendall(self, buf, flags=0):
        """
        Send "all" data on the connection. This calls send() repeatedly until
        all data is sent. If an error occurs, it's impossible to tell how much
        data has been sent.

        :param buf: The string, buffer or memoryview to send
        :param flags: (optional) Included for compatibility with the socket
                      API, the value is ignored
        :return: The number of bytes written
        """
        buf = _text_to_bytes_and_warn("buf", buf)

        if isinstance(buf, _memoryview):
            buf = buf.tobytes()
        if isinstance(buf, _buffer):
            buf = str(buf)
        if not isinstance(buf, bytes):
            raise TypeError("buf must be a memoryview, buffer or byte string")

        left_to_send = len(buf)
        total_sent = 0
        data = _ffi.new("char[]", buf)

        while left_to_send:
            result = _lib.SSL_write(self._ssl, data + total_sent, left_to_send)
            self._raise_ssl_error(self._ssl, result)
            total_sent += result
            left_to_send -= result

    def recv(self, bufsiz, flags=None):
        """
        Receive data on the connection.

        :param bufsiz: The maximum number of bytes to read
        :param flags: (optional) The only supported flag is ``MSG_PEEK``,
            all other flags are ignored.
        :return: The string read from the Connection
        """
        buf = _ffi.new("char[]", bufsiz)
        if flags is not None and flags & socket.MSG_PEEK:
            result = _lib.SSL_peek(self._ssl, buf, bufsiz)
        else:
            result = _lib.SSL_read(self._ssl, buf, bufsiz)
        self._raise_ssl_error(self._ssl, result)
        return _ffi.buffer(buf, result)[:]
    read = recv

    def recv_into(self, buffer, nbytes=None, flags=None):
        """
        Receive data on the connection and store the data into a buffer rather
        than creating a new string.

        :param buffer: The buffer to copy into.
        :param nbytes: (optional) The maximum number of bytes to read into the
            buffer. If not present, defaults to the size of the buffer. If
            larger than the size of the buffer, is reduced to the size of the
            buffer.
        :param flags: (optional) The only supported flag is ``MSG_PEEK``,
            all other flags are ignored.
        :return: The number of bytes read into the buffer.
        """
        if nbytes is None:
            nbytes = len(buffer)
        else:
            nbytes = min(nbytes, len(buffer))

        # We need to create a temporary buffer. This is annoying, it would be
        # better if we could pass memoryviews straight into the SSL_read call,
        # but right now we can't. Revisit this if CFFI gets that ability.
        buf = _ffi.new("char[]", nbytes)
        if flags is not None and flags & socket.MSG_PEEK:
            result = _lib.SSL_peek(self._ssl, buf, nbytes)
        else:
            result = _lib.SSL_read(self._ssl, buf, nbytes)
        self._raise_ssl_error(self._ssl, result)

        # This strange line is all to avoid a memory copy. The buffer protocol
        # should allow us to assign a CFFI buffer to the LHS of this line, but
        # on CPython 3.3+ that segfaults. As a workaround, we can temporarily
        # wrap it in a memoryview, except on Python 2.6 which doesn't have a
        # memoryview type.
        try:
            buffer[:result] = memoryview(_ffi.buffer(buf, result))
        except NameError:
            buffer[:result] = _ffi.buffer(buf, result)

        return result

    def _handle_bio_errors(self, bio, result):
        if _lib.BIO_should_retry(bio):
            if _lib.BIO_should_read(bio):
                raise WantReadError()
            elif _lib.BIO_should_write(bio):
                # TODO: This is untested.
                raise WantWriteError()
            elif _lib.BIO_should_io_special(bio):
                # TODO: This is untested.  I think io_special means the socket
                # BIO has a not-yet connected socket.
                raise ValueError("BIO_should_io_special")
            else:
                # TODO: This is untested.
                raise ValueError("unknown bio failure")
        else:
            # TODO: This is untested.
            _raise_current_error()

    def bio_read(self, bufsiz):
        """
        When using non-socket connections this function reads the "dirty" data
        that would have traveled away on the network.

        :param bufsiz: The maximum number of bytes to read
        :return: The string read.
        """
        if self._from_ssl is None:
            raise TypeError("Connection sock was not None")

        if not isinstance(bufsiz, integer_types):
            raise TypeError("bufsiz must be an integer")

        buf = _ffi.new("char[]", bufsiz)
        result = _lib.BIO_read(self._from_ssl, buf, bufsiz)
        if result <= 0:
            self._handle_bio_errors(self._from_ssl, result)

        return _ffi.buffer(buf, result)[:]

    def bio_write(self, buf):
        """
        When using non-socket connections this function sends "dirty" data that
        would have traveled in on the network.

        :param buf: The string to put into the memory BIO.
        :return: The number of bytes written
        """
        buf = _text_to_bytes_and_warn("buf", buf)

        if self._into_ssl is None:
            raise TypeError("Connection sock was not None")

        result = _lib.BIO_write(self._into_ssl, buf, len(buf))
        if result <= 0:
            self._handle_bio_errors(self._into_ssl, result)
        return result

    def renegotiate(self):
        """
        Renegotiate the session.

        :return: True if the renegotiation can be started, False otherwise
        :rtype: bool
        """
        if not self.renegotiate_pending():
            _openssl_assert(_lib.SSL_renegotiate(self._ssl) == 1)
            return True
        return False

    def do_handshake(self):
        """
        Perform an SSL handshake (usually called after renegotiate() or one of
        set_*_state()). This can raise the same exceptions as send and recv.

        :return: None.
        """
        result = _lib.SSL_do_handshake(self._ssl)
        self._raise_ssl_error(self._ssl, result)

    def renegotiate_pending(self):
        """
        Check if there's a renegotiation in progress, it will return False once
        a renegotiation is finished.

        :return: Whether there's a renegotiation in progress
        :rtype: bool
        """
        return _lib.SSL_renegotiate_pending(self._ssl) == 1

    def total_renegotiations(self):
        """
        Find out the total number of renegotiations.

        :return: The number of renegotiations.
        :rtype: int
        """
        return _lib.SSL_total_renegotiations(self._ssl)

    def connect(self, addr):
        """
        Connect to remote host and set up client-side SSL

        :param addr: A remote address
        :return: What the socket's connect method returns
        """
        _lib.SSL_set_connect_state(self._ssl)
        return self._socket.connect(addr)

    def connect_ex(self, addr):
        """
        Connect to remote host and set up client-side SSL. Note that if the
        socket's connect_ex method doesn't return 0, SSL won't be initialized.

        :param addr: A remove address
        :return: What the socket's connect_ex method returns
        """
        connect_ex = self._socket.connect_ex
        self.set_connect_state()
        return connect_ex(addr)

    def accept(self):
        """
        Accept incoming connection and set up SSL on it

        :return: A (conn,addr) pair where conn is a Connection and addr is an
                 address
        """
        client, addr = self._socket.accept()
        conn = Connection(self._context, client)
        conn.set_accept_state()
        return (conn, addr)

    def bio_shutdown(self):
        """
        When using non-socket connections this function signals end of
        data on the input for this connection.

        :return: None
        """
        if self._from_ssl is None:
            raise TypeError("Connection sock was not None")

        _lib.BIO_set_mem_eof_return(self._into_ssl, 0)

    def shutdown(self):
        """
        Send closure alert

        :return: True if the shutdown completed successfully (i.e. both sides
                 have sent closure alerts), false otherwise (i.e. you have to
                 wait for a ZeroReturnError on a recv() method call
        """
        result = _lib.SSL_shutdown(self._ssl)
        if result < 0:
            self._raise_ssl_error(self._ssl, result)
        elif result > 0:
            return True
        else:
            return False

    def get_cipher_list(self):
        """
        Retrieve the list of ciphers used by the Connection object.

        :return: A list of native cipher strings.
        """
        ciphers = []
        for i in count():
            result = _lib.SSL_get_cipher_list(self._ssl, i)
            if result == _ffi.NULL:
                break
            ciphers.append(_native(_ffi.string(result)))
        return ciphers

    def get_client_ca_list(self):
        """
        Get CAs whose certificates are suggested for client authentication.

        :return: If this is a server connection, a list of X509Names
            representing the acceptable CAs as set by
            :py:meth:`OpenSSL.SSL.Context.set_client_ca_list` or
            :py:meth:`OpenSSL.SSL.Context.add_client_ca`.  If this is a client
            connection, the list of such X509Names sent by the server, or an
            empty list if that has not yet happened.
        """
        ca_names = _lib.SSL_get_client_CA_list(self._ssl)
        if ca_names == _ffi.NULL:
            # TODO: This is untested.
            return []

        result = []
        for i in range(_lib.sk_X509_NAME_num(ca_names)):
            name = _lib.sk_X509_NAME_value(ca_names, i)
            copy = _lib.X509_NAME_dup(name)
            _openssl_assert(copy != _ffi.NULL)

            pyname = X509Name.__new__(X509Name)
            pyname._name = _ffi.gc(copy, _lib.X509_NAME_free)
            result.append(pyname)
        return result

    def makefile(self):
        """
        The makefile() method is not implemented, since there is no dup
        semantics for SSL connections

        :raise: NotImplementedError
        """
        raise NotImplementedError(
            "Cannot make file object of OpenSSL.SSL.Connection")

    def get_app_data(self):
        """
        Get application data

        :return: The application data
        """
        return self._app_data

    def set_app_data(self, data):
        """
        Set application data

        :param data - The application data
        :return: None
        """
        self._app_data = data

    def get_shutdown(self):
        """
        Get shutdown state

        :return: The shutdown state, a bitvector of SENT_SHUTDOWN,
            RECEIVED_SHUTDOWN.
        """
        return _lib.SSL_get_shutdown(self._ssl)

    def set_shutdown(self, state):
        """
        Set shutdown state

        :param state - bitvector of SENT_SHUTDOWN, RECEIVED_SHUTDOWN.
        :return: None
        """
        if not isinstance(state, integer_types):
            raise TypeError("state must be an integer")

        _lib.SSL_set_shutdown(self._ssl, state)

    def get_state_string(self):
        """
        Retrieve a verbose string detailing the state of the Connection.

        :return: A string representing the state
        :rtype: bytes
        """
        return _ffi.string(_lib.SSL_state_string_long(self._ssl))

    def server_random(self):
        """
        Get a copy of the server hello nonce.

        :return: A string representing the state
        """
        session = _lib.SSL_get_session(self._ssl)
        if session == _ffi.NULL:
            return None
        length = _lib.SSL_get_server_random(self._ssl, _ffi.NULL, 0)
        assert length > 0
        outp = _ffi.new("unsigned char[]", length)
        _lib.SSL_get_server_random(self._ssl, outp, length)
        return _ffi.buffer(outp, length)[:]

    def client_random(self):
        """
        Get a copy of the client hello nonce.

        :return: A string representing the state
        """
        session = _lib.SSL_get_session(self._ssl)
        if session == _ffi.NULL:
            return None

        length = _lib.SSL_get_client_random(self._ssl, _ffi.NULL, 0)
        assert length > 0
        outp = _ffi.new("unsigned char[]", length)
        _lib.SSL_get_client_random(self._ssl, outp, length)
        return _ffi.buffer(outp, length)[:]

    def master_key(self):
        """
        Get a copy of the master key.

        :return: A string representing the state
        """
        session = _lib.SSL_get_session(self._ssl)
        if session == _ffi.NULL:
            return None

        length = _lib.SSL_SESSION_get_master_key(session, _ffi.NULL, 0)
        assert length > 0
        outp = _ffi.new("unsigned char[]", length)
        _lib.SSL_SESSION_get_master_key(session, outp, length)
        return _ffi.buffer(outp, length)[:]

    def sock_shutdown(self, *args, **kwargs):
        """
        See shutdown(2)

        :return: What the socket's shutdown() method returns
        """
        return self._socket.shutdown(*args, **kwargs)

    def get_peer_certificate(self):
        """
        Retrieve the other side's certificate (if any)

        :return: The peer's certificate
        """
        cert = _lib.SSL_get_peer_certificate(self._ssl)
        if cert != _ffi.NULL:
            pycert = X509.__new__(X509)
            pycert._x509 = _ffi.gc(cert, _lib.X509_free)
            return pycert
        return None

    def get_peer_cert_chain(self):
        """
        Retrieve the other side's certificate (if any)

        :return: A list of X509 instances giving the peer's certificate chain,
                 or None if it does not have one.
        """
        cert_stack = _lib.SSL_get_peer_cert_chain(self._ssl)
        if cert_stack == _ffi.NULL:
            return None

        result = []
        for i in range(_lib.sk_X509_num(cert_stack)):
            # TODO could incref instead of dup here
            cert = _lib.X509_dup(_lib.sk_X509_value(cert_stack, i))
            pycert = X509.__new__(X509)
            pycert._x509 = _ffi.gc(cert, _lib.X509_free)
            result.append(pycert)
        return result

    def want_read(self):
        """
        Checks if more data has to be read from the transport layer to complete
        an operation.

        :return: True iff more data has to be read
        """
        return _lib.SSL_want_read(self._ssl)

    def want_write(self):
        """
        Checks if there is data to write to the transport layer to complete an
        operation.

        :return: True iff there is data to write
        """
        return _lib.SSL_want_write(self._ssl)

    def set_accept_state(self):
        """
        Set the connection to work in server mode. The handshake will be
        handled automatically by read/write.

        :return: None
        """
        _lib.SSL_set_accept_state(self._ssl)

    def set_connect_state(self):
        """
        Set the connection to work in client mode. The handshake will be
        handled automatically by read/write.

        :return: None
        """
        _lib.SSL_set_connect_state(self._ssl)

    def get_session(self):
        """
        Returns the Session currently used.

        @return: An instance of :py:class:`OpenSSL.SSL.Session` or
            :py:obj:`None` if no session exists.
        """
        session = _lib.SSL_get1_session(self._ssl)
        if session == _ffi.NULL:
            return None

        pysession = Session.__new__(Session)
        pysession._session = _ffi.gc(session, _lib.SSL_SESSION_free)
        return pysession

    def set_session(self, session):
        """
        Set the session to be used when the TLS/SSL connection is established.

        :param session: A Session instance representing the session to use.
        :returns: None
        """
        if not isinstance(session, Session):
            raise TypeError("session must be a Session instance")

        result = _lib.SSL_set_session(self._ssl, session._session)
        if not result:
            _raise_current_error()

    def _get_finished_message(self, function):
        """
        Helper to implement :py:meth:`get_finished` and
        :py:meth:`get_peer_finished`.

        :param function: Either :py:data:`SSL_get_finished`: or
            :py:data:`SSL_get_peer_finished`.

        :return: :py:data:`None` if the desired message has not yet been
            received, otherwise the contents of the message.
        :rtype: :py:class:`bytes` or :py:class:`NoneType`
        """
        # The OpenSSL documentation says nothing about what might happen if the
        # count argument given is zero.  Specifically, it doesn't say whether
        # the output buffer may be NULL in that case or not.  Inspection of the
        # implementation reveals that it calls memcpy() unconditionally.
        # Section 7.1.4, paragraph 1 of the C standard suggests that
        # memcpy(NULL, source, 0) is not guaranteed to produce defined (let
        # alone desirable) behavior (though it probably does on just about
        # every implementation...)
        #
        # Allocate a tiny buffer to pass in (instead of just passing NULL as
        # one might expect) for the initial call so as to be safe against this
        # potentially undefined behavior.
        empty = _ffi.new("char[]", 0)
        size = function(self._ssl, empty, 0)
        if size == 0:
            # No Finished message so far.
            return None

        buf = _ffi.new("char[]", size)
        function(self._ssl, buf, size)
        return _ffi.buffer(buf, size)[:]

    def get_finished(self):
        """
        Obtain the latest `handshake finished` message sent to the peer.

        :return: The contents of the message or :py:obj:`None` if the TLS
            handshake has not yet completed.
        :rtype: :py:class:`bytes` or :py:class:`NoneType`
        """
        return self._get_finished_message(_lib.SSL_get_finished)

    def get_peer_finished(self):
        """
        Obtain the latest `handshake finished` message received from the peer.

        :return: The contents of the message or :py:obj:`None` if the TLS
            handshake has not yet completed.
        :rtype: :py:class:`bytes` or :py:class:`NoneType`
        """
        return self._get_finished_message(_lib.SSL_get_peer_finished)

    def get_cipher_name(self):
        """
        Obtain the name of the currently used cipher.

        :returns: The name of the currently used cipher or :py:obj:`None`
            if no connection has been established.
        :rtype: :py:class:`unicode` or :py:class:`NoneType`
        """
        cipher = _lib.SSL_get_current_cipher(self._ssl)
        if cipher == _ffi.NULL:
            return None
        else:
            name = _ffi.string(_lib.SSL_CIPHER_get_name(cipher))
            return name.decode("utf-8")

    def get_cipher_bits(self):
        """
        Obtain the number of secret bits of the currently used cipher.

        :returns: The number of secret bits of the currently used cipher
            or :py:obj:`None` if no connection has been established.
        :rtype: :py:class:`int` or :py:class:`NoneType`
        """
        cipher = _lib.SSL_get_current_cipher(self._ssl)
        if cipher == _ffi.NULL:
            return None
        else:
            return _lib.SSL_CIPHER_get_bits(cipher, _ffi.NULL)

    def get_cipher_version(self):
        """
        Obtain the protocol version of the currently used cipher.

        :returns: The protocol name of the currently used cipher
            or :py:obj:`None` if no connection has been established.
        :rtype: :py:class:`unicode` or :py:class:`NoneType`
        """
        cipher = _lib.SSL_get_current_cipher(self._ssl)
        if cipher == _ffi.NULL:
            return None
        else:
            version = _ffi.string(_lib.SSL_CIPHER_get_version(cipher))
            return version.decode("utf-8")

    def get_protocol_version_name(self):
        """
        Obtain the protocol version of the current connection.

        :returns: The TLS version of the current connection, for example
            the value for TLS 1.2 would be ``TLSv1.2``or ``Unknown``
            for connections that were not successfully established.
        :rtype: :py:class:`unicode`
        """
        version = _ffi.string(_lib.SSL_get_version(self._ssl))
        return version.decode("utf-8")

    def get_protocol_version(self):
        """
        Obtain the protocol version of the current connection.

        :returns: The TLS version of the current connection, for example
            the value for TLS 1 would be 0x769.
        :rtype: :py:class:`int`
        """
        version = _lib.SSL_version(self._ssl)
        return version

    @_requires_npn
    def get_next_proto_negotiated(self):
        """
        Get the protocol that was negotiated by NPN.
        """
        data = _ffi.new("unsigned char **")
        data_len = _ffi.new("unsigned int *")

        _lib.SSL_get0_next_proto_negotiated(self._ssl, data, data_len)

        return _ffi.buffer(data[0], data_len[0])[:]

    @_requires_alpn
    def set_alpn_protos(self, protos):
        """
        Specify the client's ALPN protocol list.

        These protocols are offered to the server during protocol negotiation.

        :param protos: A list of the protocols to be offered to the server.
            This list should be a Python list of bytestrings representing the
            protocols to offer, e.g. ``[b'http/1.1', b'spdy/2']``.
        """
        # Take the list of protocols and join them together, prefixing them
        # with their lengths.
        protostr = b''.join(
            chain.from_iterable((int2byte(len(p)), p) for p in protos)
        )

        # Build a C string from the list. We don't need to save this off
        # because OpenSSL immediately copies the data out.
        input_str = _ffi.new("unsigned char[]", protostr)
        input_str_len = _ffi.cast("unsigned", len(protostr))
        _lib.SSL_set_alpn_protos(self._ssl, input_str, input_str_len)

    @_requires_alpn
    def get_alpn_proto_negotiated(self):
        """
        Get the protocol that was negotiated by ALPN.
        """
        data = _ffi.new("unsigned char **")
        data_len = _ffi.new("unsigned int *")

        _lib.SSL_get0_alpn_selected(self._ssl, data, data_len)

        if not data_len:
            return b''

        return _ffi.buffer(data[0], data_len[0])[:]


ConnectionType = Connection

# This is similar to the initialization calls at the end of OpenSSL/crypto.py
# but is exercised mostly by the Context initializer.
_lib.SSL_library_init()
