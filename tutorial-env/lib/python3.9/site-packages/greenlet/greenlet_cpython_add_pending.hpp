#ifndef GREENLET_CPYTHON_ADD_PENDING_HPP
#define GREENLET_CPYTHON_ADD_PENDING_HPP

#if (PY_VERSION_HEX >= 0x30800A0 && PY_VERSION_HEX < 0x3090000) && !(defined(_WIN32) || defined(WIN32))
// XXX: From Python 3.8a3 [1] up until Python 3.9a6 [2][3],
// ``Py_AddPendingCall`` would try to produce a Python exception if
// the interpreter was in the beginning of shutting down when this
// function is called. However, ``Py_AddPendingCall`` doesn't require
// the GIL, and we are absolutely not holding it when we make that
// call. That means that trying to create the Python exception is
// using the C API in an undefined state; here the C API detects this
// and aborts the process with an error ("Fatal Python error: Python
// memory allocator called without holding the GIL": Add ->
// PyErr_SetString -> PyUnicode_New -> PyObject_Malloc). This arises
// (obviously) in multi-threaded programs and happens if one thread is
// exiting and cleaning up its thread-local data while the other
// thread is trying to shut down the interpreter. A crash on shutdown
// is still a crash and could result in data loss (e.g., daemon
// threads are still running, pending signal handlers may be present,
// buffers may not be flushed, there may be __del__ that need run,
// etc), so we have to work around it.
//
// Of course, we can (and do) check for whether the interpreter is
// shutting down before calling ``Py_AddPendingCall``, but that's a
// race condition since we don't hold the GIL, and so we may not
// actually get the right answer. Plus, ``Py_FinalizeEx`` actually
// calls ``_Py_FinishPendingCalls`` (which sets the pending->finishing
// flag, which is used to gate creating the exceptioen) *before*
// publishing any other data that would let us detect the shutdown
// (such as runtime->finalizing). So that point is moot.
//
// Our solution for those versions is to inline the same code, without
// the problematic bit that sets the exception. Unfortunately, all of
// the structure definitions are private/opaque, *and* we can't
// actually count on being able to include their definitions from
// ``internal/pycore_*``, because on some platforms those header files
// are incomplete (i.e., on macOS with macports 3.8, the includes are
// fine, but on Ubuntu jammy with 3.8 from ppa:deadsnakes or GitHub
// Actions 3.8 (I think it's Ubuntu 18.04), they con't be used; at
// least, I couldn't get them to work). So we need to define the
// structures and _PyRuntime data member ourself. Yet more
// unfortunately, _PyRuntime  won't link on Windows, so we can only do
// this on other platforms.
//
// [1] https://github.com/python/cpython/commit/842a2f07f2f08a935ef470bfdaeef40f87490cfc
// [2] https://github.com/python/cpython/commit/cfc3c2f8b34d3864717ab584c5b6c260014ba55a
// [3] https://github.com/python/cpython/issues/81308
# define GREENLET_BROKEN_PY_ADD_PENDING 1

// When defining these structures, the important thing is to get
// binary compatibility, i.e., structure layout. For that, we only
// need to define fields up to the ones we use; after that they're
// irrelevant UNLESS the structure is included in another structure
// *before* the structure we're interested in --- in that case, it
// must be complete. Ellipsis indicate elided trailing members.
// Pointer types are changed to void* to keep from having to define
// more structures.

// From "internal/pycore_atomic.h"

// There are several different definitions of this, including the
// plain ``int`` version, a ``volatile int`` and an ``_Atomic int``
// I don't think any of those change the size/layout.
typedef struct _Py_atomic_int {
    volatile int _value;
} _Py_atomic_int;

// This needs too much infrastructure, so we just do a regular store.
#define _Py_atomic_store_relaxed(ATOMIC_VAL, NEW_VAL) \
    (ATOMIC_VAL)->_value = NEW_VAL



// From "internal/pycore_pymem.h"
#define NUM_GENERATIONS 3


struct gc_generation {
    PyGC_Head head; // We already have this defined.
    int threshold;
    int count;
};
struct gc_generation_stats {
    Py_ssize_t collections;
    Py_ssize_t collected;
    Py_ssize_t uncollectable;
};

struct _gc_runtime_state {
    void *trash_delete_later;
    int trash_delete_nesting;
    int enabled;
    int debug;
    struct gc_generation generations[NUM_GENERATIONS];
    void *generation0;
    struct gc_generation permanent_generation;
    struct gc_generation_stats generation_stats[NUM_GENERATIONS];
    int collecting;
    void *garbage;
    void *callbacks;
    Py_ssize_t long_lived_total;
    Py_ssize_t long_lived_pending;
};

// From "internal/pycore_pystate.h"
struct _pending_calls {
    int finishing;
    PyThread_type_lock lock;
    _Py_atomic_int calls_to_do;
    int async_exc;
#define NPENDINGCALLS 32
    struct {
        int (*func)(void *);
        void *arg;
    } calls[NPENDINGCALLS];
    int first;
    int last;
};

struct _ceval_runtime_state {
    int recursion_limit;
    int tracing_possible;
    _Py_atomic_int eval_breaker;
    _Py_atomic_int gil_drop_request;
    struct _pending_calls pending;
    // ...
};

typedef struct pyruntimestate {
    int preinitializing;
    int preinitialized;
    int core_initialized;
    int initialized;
    void *finalizing;

    struct pyinterpreters {
        PyThread_type_lock mutex;
        void *head;
        void *main;
        int64_t next_id;
    } interpreters;
    // XXX Remove this field once we have a tp_* slot.
    struct _xidregistry {
        PyThread_type_lock mutex;
        void *head;
    } xidregistry;

    unsigned long main_thread;

#define NEXITFUNCS 32
    void (*exitfuncs[NEXITFUNCS])(void);
    int nexitfuncs;

    struct _gc_runtime_state gc;
    struct _ceval_runtime_state ceval;
    // ...
} _PyRuntimeState;

#define SIGNAL_PENDING_CALLS(ceval) \
    do { \
        _Py_atomic_store_relaxed(&(ceval)->pending.calls_to_do, 1); \
        _Py_atomic_store_relaxed(&(ceval)->eval_breaker, 1); \
    } while (0)

extern _PyRuntimeState _PyRuntime;

#else
# define GREENLET_BROKEN_PY_ADD_PENDING 0
#endif


#endif
