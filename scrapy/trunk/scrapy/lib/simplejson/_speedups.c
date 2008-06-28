#include "Python.h"
#if PY_VERSION_HEX < 0x02050000 && !defined(PY_SSIZE_T_MIN)
typedef int Py_ssize_t;
#define PY_SSIZE_T_MAX INT_MAX
#define PY_SSIZE_T_MIN INT_MIN
#endif

static Py_ssize_t
ascii_escape_char(Py_UNICODE c, char *output, Py_ssize_t chars);
static PyObject *
ascii_escape_unicode(PyObject *pystr);
static PyObject *
ascii_escape_str(PyObject *pystr);
static PyObject *
py_encode_basestring_ascii(PyObject* self __attribute__((__unused__)), PyObject *pystr);
void init_speedups(void);

#define S_CHAR(c) (c >= ' ' && c <= '~' && c != '\\' && c != '/' && c != '"')

#define MIN_EXPANSION 6
#ifdef Py_UNICODE_WIDE
#define MAX_EXPANSION (2 * MIN_EXPANSION)
#else
#define MAX_EXPANSION MIN_EXPANSION
#endif

static Py_ssize_t
ascii_escape_char(Py_UNICODE c, char *output, Py_ssize_t chars) {
    Py_UNICODE x;
    output[chars++] = '\\';
    switch (c) {
        case '/': output[chars++] = (char)c; break;
        case '\\': output[chars++] = (char)c; break;
        case '"': output[chars++] = (char)c; break;
        case '\b': output[chars++] = 'b'; break;
        case '\f': output[chars++] = 'f'; break;
        case '\n': output[chars++] = 'n'; break;
        case '\r': output[chars++] = 'r'; break;
        case '\t': output[chars++] = 't'; break;
        default:
#ifdef Py_UNICODE_WIDE
            if (c >= 0x10000) {
                /* UTF-16 surrogate pair */
                Py_UNICODE v = c - 0x10000;
                c = 0xd800 | ((v >> 10) & 0x3ff);
                output[chars++] = 'u';
                x = (c & 0xf000) >> 12;
                output[chars++] = (x < 10) ? '0' + x : 'a' + (x - 10);
                x = (c & 0x0f00) >> 8;
                output[chars++] = (x < 10) ? '0' + x : 'a' + (x - 10);
                x = (c & 0x00f0) >> 4;
                output[chars++] = (x < 10) ? '0' + x : 'a' + (x - 10);
                x = (c & 0x000f);
                output[chars++] = (x < 10) ? '0' + x : 'a' + (x - 10);
                c = 0xdc00 | (v & 0x3ff);
                output[chars++] = '\\';
            }
#endif
            output[chars++] = 'u';
            x = (c & 0xf000) >> 12;
            output[chars++] = (x < 10) ? '0' + x : 'a' + (x - 10);
            x = (c & 0x0f00) >> 8;
            output[chars++] = (x < 10) ? '0' + x : 'a' + (x - 10);
            x = (c & 0x00f0) >> 4;
            output[chars++] = (x < 10) ? '0' + x : 'a' + (x - 10);
            x = (c & 0x000f);
            output[chars++] = (x < 10) ? '0' + x : 'a' + (x - 10);
    }
    return chars;
}

static PyObject *
ascii_escape_unicode(PyObject *pystr) {
    Py_ssize_t i;
    Py_ssize_t input_chars;
    Py_ssize_t output_size;
    Py_ssize_t chars;
    PyObject *rval;
    char *output;
    Py_UNICODE *input_unicode;

    input_chars = PyUnicode_GET_SIZE(pystr);
    input_unicode = PyUnicode_AS_UNICODE(pystr);
    /* One char input can be up to 6 chars output, estimate 4 of these */
    output_size = 2 + (MIN_EXPANSION * 4) + input_chars;
    rval = PyString_FromStringAndSize(NULL, output_size);
    if (rval == NULL) {
        return NULL;
    }
    output = PyString_AS_STRING(rval);
    chars = 0;
    output[chars++] = '"';
    for (i = 0; i < input_chars; i++) {
        Py_UNICODE c = input_unicode[i];
        if (S_CHAR(c)) {
            output[chars++] = (char)c;
        } else {
            chars = ascii_escape_char(c, output, chars);
        }
        if (output_size - chars < (1 + MAX_EXPANSION)) {
            /* There's more than four, so let's resize by a lot */
            output_size *= 2;
            /* This is an upper bound */
            if (output_size > 2 + (input_chars * MAX_EXPANSION)) {
                output_size = 2 + (input_chars * MAX_EXPANSION);
            }
            if (_PyString_Resize(&rval, output_size) == -1) {
                return NULL;
            }
            output = PyString_AS_STRING(rval);
        }
    }
    output[chars++] = '"';
    if (_PyString_Resize(&rval, chars) == -1) {
        return NULL;
    }
    return rval;
}

static PyObject *
ascii_escape_str(PyObject *pystr) {
    Py_ssize_t i;
    Py_ssize_t input_chars;
    Py_ssize_t output_size;
    Py_ssize_t chars;
    PyObject *rval;
    char *output;
    char *input_str;

    input_chars = PyString_GET_SIZE(pystr);
    input_str = PyString_AS_STRING(pystr);
    /* One char input can be up to 6 chars output, estimate 4 of these */
    output_size = 2 + (MIN_EXPANSION * 4) + input_chars;
    rval = PyString_FromStringAndSize(NULL, output_size);
    if (rval == NULL) {
        return NULL;
    }
    output = PyString_AS_STRING(rval);
    chars = 0;
    output[chars++] = '"';
    for (i = 0; i < input_chars; i++) {
        Py_UNICODE c = (Py_UNICODE)input_str[i];
        if (S_CHAR(c)) {
            output[chars++] = (char)c;
        } else if (c > 0x7F) {
            /* We hit a non-ASCII character, bail to unicode mode */
            PyObject *uni;
            Py_DECREF(rval);
            uni = PyUnicode_DecodeUTF8(input_str, input_chars, "strict");
            if (uni == NULL) {
                return NULL;
            }
            rval = ascii_escape_unicode(uni);
            Py_DECREF(uni);
            return rval;
        } else {
            chars = ascii_escape_char(c, output, chars);
        }
        /* An ASCII char can't possibly expand to a surrogate! */
        if (output_size - chars < (1 + MIN_EXPANSION)) {
            /* There's more than four, so let's resize by a lot */
            output_size *= 2;
            if (output_size > 2 + (input_chars * MIN_EXPANSION)) {
                output_size = 2 + (input_chars * MIN_EXPANSION);
            }
            if (_PyString_Resize(&rval, output_size) == -1) {
                return NULL;
            }
            output = PyString_AS_STRING(rval);
        }
    }
    output[chars++] = '"';
    if (_PyString_Resize(&rval, chars) == -1) {
        return NULL;
    }
    return rval;
}

PyDoc_STRVAR(pydoc_encode_basestring_ascii,
    "encode_basestring_ascii(basestring) -> str\n"
    "\n"
    "..."
);

static PyObject *
py_encode_basestring_ascii(PyObject* self __attribute__((__unused__)), PyObject *pystr) {
    /* METH_O */
    if (PyString_Check(pystr)) {
        return ascii_escape_str(pystr);
    } else if (PyUnicode_Check(pystr)) {
        return ascii_escape_unicode(pystr);
    }
    PyErr_SetString(PyExc_TypeError, "first argument must be a string");
    return NULL;
}

#define DEFN(n, k) \
    {  \
        #n, \
        (PyCFunction)py_ ##n, \
        k, \
        pydoc_ ##n \
    }
static PyMethodDef speedups_methods[] = {
    DEFN(encode_basestring_ascii, METH_O),
    {}
};
#undef DEFN

void
init_speedups(void)
{
    PyObject *m;
    m = Py_InitModule4("_speedups", speedups_methods, NULL, NULL, PYTHON_API_VERSION);
}
