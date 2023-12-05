/* -*- indent-tabs-mode: nil; tab-width: 4; -*- */
/* Format with:
 *  clang-format -i --style=file src/greenlet/greenlet.c
 *
 *
 * Fix missing braces with:
 *   clang-tidy src/greenlet/greenlet.c -fix -checks="readability-braces-around-statements"
*/
#include <cstdlib>
#include <string>
#include <algorithm>
#include <exception>


#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "structmember.h" // PyMemberDef

#include "greenlet_internal.hpp"
// Code after this point can assume access to things declared in stdint.h,
// including the fixed-width types. This goes for the platform-specific switch functions
// as well.
#include "greenlet_refs.hpp"
#include "greenlet_slp_switch.hpp"
#include "greenlet_thread_state.hpp"
#include "greenlet_thread_support.hpp"
#include "greenlet_greenlet.hpp"

#include "TGreenletGlobals.cpp"
#include "TThreadStateDestroy.cpp"
#include "TGreenlet.cpp"
#include "TMainGreenlet.cpp"
#include "TUserGreenlet.cpp"
#include "TBrokenGreenlet.cpp"
#include "TExceptionState.cpp"
#include "TPythonState.cpp"
#include "TStackState.cpp"


using greenlet::LockGuard;
using greenlet::LockInitError;
using greenlet::PyErrOccurred;
using greenlet::Require;

using greenlet::g_handle_exit;
using greenlet::single_result;

using greenlet::Greenlet;
using greenlet::UserGreenlet;
using greenlet::MainGreenlet;
using greenlet::BrokenGreenlet;
using greenlet::ThreadState;
using greenlet::PythonState;



// ******* Implementation of things from included files
template<typename T, greenlet::refs::TypeChecker TC>
greenlet::refs::_BorrowedGreenlet<T, TC>& greenlet::refs::_BorrowedGreenlet<T, TC>::operator=(const greenlet::refs::BorrowedObject& other)
{
    this->_set_raw_pointer(static_cast<PyObject*>(other));
    return *this;
}

template <typename T, greenlet::refs::TypeChecker TC>
inline greenlet::refs::_BorrowedGreenlet<T, TC>::operator Greenlet*() const noexcept
{
    if (!this->p) {
        return nullptr;
    }
    return reinterpret_cast<PyGreenlet*>(this->p)->pimpl;
}

template<typename T, greenlet::refs::TypeChecker TC>
greenlet::refs::_BorrowedGreenlet<T, TC>::_BorrowedGreenlet(const BorrowedObject& p)
    : BorrowedReference<T, TC>(nullptr)
{

    this->_set_raw_pointer(p.borrow());
}

template <typename T, greenlet::refs::TypeChecker TC>
inline greenlet::refs::_OwnedGreenlet<T, TC>::operator Greenlet*() const noexcept
{
    if (!this->p) {
        return nullptr;
    }
    return reinterpret_cast<PyGreenlet*>(this->p)->pimpl;
}



#ifdef __clang__
#    pragma clang diagnostic push
#    pragma clang diagnostic ignored "-Wmissing-field-initializers"
#    pragma clang diagnostic ignored "-Wwritable-strings"
#elif defined(__GNUC__)
#    pragma GCC diagnostic push
//  warning: ISO C++ forbids converting a string constant to ‘char*’
// (The python APIs aren't const correct and accept writable char*)
#    pragma GCC diagnostic ignored "-Wwrite-strings"
#endif


/***********************************************************

A PyGreenlet is a range of C stack addresses that must be
saved and restored in such a way that the full range of the
stack contains valid data when we switch to it.

Stack layout for a greenlet:

               |     ^^^       |
               |  older data   |
               |               |
  stack_stop . |_______________|
        .      |               |
        .      | greenlet data |
        .      |   in stack    |
        .    * |_______________| . .  _____________  stack_copy + stack_saved
        .      |               |     |             |
        .      |     data      |     |greenlet data|
        .      |   unrelated   |     |    saved    |
        .      |      to       |     |   in heap   |
 stack_start . |     this      | . . |_____________| stack_copy
               |   greenlet    |
               |               |
               |  newer data   |
               |     vvv       |


Note that a greenlet's stack data is typically partly at its correct
place in the stack, and partly saved away in the heap, but always in
the above configuration: two blocks, the more recent one in the heap
and the older one still in the stack (either block may be empty).

Greenlets are chained: each points to the previous greenlet, which is
the one that owns the data currently in the C stack above my
stack_stop.  The currently running greenlet is the first element of
this chain.  The main (initial) greenlet is the last one.  Greenlets
whose stack is entirely in the heap can be skipped from the chain.

The chain is not related to execution order, but only to the order
in which bits of C stack happen to belong to greenlets at a particular
point in time.

The main greenlet doesn't have a stack_stop: it is responsible for the
complete rest of the C stack, and we don't know where it begins.  We
use (char*) -1, the largest possible address.

States:
  stack_stop == NULL && stack_start == NULL:  did not start yet
  stack_stop != NULL && stack_start == NULL:  already finished
  stack_stop != NULL && stack_start != NULL:  active

The running greenlet's stack_start is undefined but not NULL.

 ***********************************************************/

static PyGreenlet*
green_create_main(ThreadState* state)
{
    PyGreenlet* gmain;

    /* create the main greenlet for this thread */
    gmain = (PyGreenlet*)PyType_GenericAlloc(&PyGreenlet_Type, 0);
    if (gmain == NULL) {
        Py_FatalError("green_create_main failed to alloc");
        return NULL;
    }
    new MainGreenlet(gmain, state);

    assert(Py_REFCNT(gmain) == 1);
    return gmain;
}



/***********************************************************/

/* Some functions must not be inlined:
   * slp_restore_state, when inlined into slp_switch might cause
     it to restore stack over its own local variables
   * slp_save_state, when inlined would add its own local
     variables to the saved stack, wasting space
   * slp_switch, cannot be inlined for obvious reasons
   * g_initialstub, when inlined would receive a pointer into its
     own stack frame, leading to incomplete stack save/restore

g_initialstub is a member function and declared virtual so that the
compiler always calls it through a vtable.

slp_save_state and slp_restore_state are also member functions. They
are called from trampoline functions that themselves are declared as
not eligible for inlining.
*/

extern "C" {
static int GREENLET_NOINLINE(slp_save_state_trampoline)(char* stackref)
{
    return switching_thread_state->slp_save_state(stackref);
}
static void GREENLET_NOINLINE(slp_restore_state_trampoline)()
{
    switching_thread_state->slp_restore_state();
}
}


/***********************************************************/

static PyGreenlet*
green_new(PyTypeObject* type, PyObject* UNUSED(args), PyObject* UNUSED(kwds))
{
    PyGreenlet* o =
        (PyGreenlet*)PyBaseObject_Type.tp_new(type, mod_globs->empty_tuple, mod_globs->empty_dict);
    if (o) {
        new UserGreenlet(o, GET_THREAD_STATE().state().borrow_current());
        assert(Py_REFCNT(o) == 1);
    }
    return o;
}

static PyGreenlet*
green_unswitchable_new(PyTypeObject* type, PyObject* UNUSED(args), PyObject* UNUSED(kwds))
{
    PyGreenlet* o =
        (PyGreenlet*)PyBaseObject_Type.tp_new(type, mod_globs->empty_tuple, mod_globs->empty_dict);
    if (o) {
        new BrokenGreenlet(o, GET_THREAD_STATE().state().borrow_current());
        assert(Py_REFCNT(o) == 1);
    }
    return o;
}

static int
green_setrun(BorrowedGreenlet self, BorrowedObject nrun, void* c);
static int
green_setparent(BorrowedGreenlet self, BorrowedObject nparent, void* c);

static int
green_init(BorrowedGreenlet self, BorrowedObject args, BorrowedObject kwargs)
{
    PyArgParseParam run;
    PyArgParseParam nparent;
    static const char* const kwlist[] = {
        "run",
        "parent",
        NULL
    };

    // recall: The O specifier does NOT increase the reference count.
    if (!PyArg_ParseTupleAndKeywords(
             args, kwargs, "|OO:green", (char**)kwlist, &run, &nparent)) {
        return -1;
    }

    if (run) {
        if (green_setrun(self, run, NULL)) {
            return -1;
        }
    }
    if (nparent && !nparent.is_None()) {
        return green_setparent(self, nparent, NULL);
    }
    return 0;
}



static int
green_traverse(PyGreenlet* self, visitproc visit, void* arg)
{
    // We must only visit referenced objects, i.e. only objects
    // Py_INCREF'ed by this greenlet (directly or indirectly):
    //
    // - stack_prev is not visited: holds previous stack pointer, but it's not
    //    referenced
    // - frames are not visited as we don't strongly reference them;
    //    alive greenlets are not garbage collected
    //    anyway. This can be a problem, however, if this greenlet is
    //    never allowed to finish, and is referenced from the frame: we
    //    have an uncollectible cycle in that case. Note that the
    //    frame object itself is also frequently not even tracked by the GC
    //    starting with Python 3.7 (frames are allocated by the
    //    interpreter untracked, and only become tracked when their
    //    evaluation is finished if they have a refcount > 1). All of
    //    this is to say that we should probably strongly reference
    //    the frame object. Doing so, while always allowing GC on a
    //    greenlet, solves several leaks for us.

    Py_VISIT(self->dict);
    if (!self->pimpl) {
        // Hmm. I have seen this at interpreter shutdown time,
        // I think. That's very odd because this doesn't go away until
        // we're ``green_dealloc()``, at which point we shouldn't be
        // traversed anymore.
        return 0;
    }

    return self->pimpl->tp_traverse(visit, arg);
}

static int
green_is_gc(BorrowedGreenlet self)
{
    int result = 0;
    /* Main greenlet can be garbage collected since it can only
       become unreachable if the underlying thread exited.
       Active greenlets --- including those that are suspended ---
       cannot be garbage collected, however.
    */
    if (self->main() || !self->active()) {
        result = 1;
    }
    // The main greenlet pointer will eventually go away after the thread dies.
    if (self->was_running_in_dead_thread()) {
        // Our thread is dead! We can never run again. Might as well
        // GC us. Note that if a tuple containing only us and other
        // immutable objects had been scanned before this, when we
        // would have returned 0, the tuple will take itself out of GC
        // tracking and never be investigated again. So that could
        // result in both us and the tuple leaking due to an
        // unreachable/uncollectible reference. The same goes for
        // dictionaries.
        //
        // It's not a great idea to be changing our GC state on the
        // fly.
        result = 1;
    }
    return result;
}


static int
green_clear(PyGreenlet* self)
{
    /* Greenlet is only cleared if it is about to be collected.
       Since active greenlets are not garbage collectable, we can
       be sure that, even if they are deallocated during clear,
       nothing they reference is in unreachable or finalizers,
       so even if it switches we are relatively safe. */
    // XXX: Are we responsible for clearing weakrefs here?
    Py_CLEAR(self->dict);
    return self->pimpl->tp_clear();
}

/**
 * Returns 0 on failure (the object was resurrected) or 1 on success.
 **/
static int
_green_dealloc_kill_started_non_main_greenlet(BorrowedGreenlet self)
{
    /* Hacks hacks hacks copied from instance_dealloc() */
    /* Temporarily resurrect the greenlet. */
    assert(self.REFCNT() == 0);
    Py_SET_REFCNT(self.borrow(), 1);
    /* Save the current exception, if any. */
    PyErrPieces saved_err;
    try {
        // BY THE TIME WE GET HERE, the state may actually be going
        // away
        // if we're shutting down the interpreter and freeing thread
        // entries,
        // this could result in freeing greenlets that were leaked. So
        // we can't try to read the state.
        self->deallocing_greenlet_in_thread(
              self->thread_state()
              ? static_cast<ThreadState*>(GET_THREAD_STATE())
              : nullptr);
    }
    catch (const PyErrOccurred&) {
        PyErr_WriteUnraisable(self.borrow_o());
        /* XXX what else should we do? */
    }
    /* Check for no resurrection must be done while we keep
     * our internal reference, otherwise PyFile_WriteObject
     * causes recursion if using Py_INCREF/Py_DECREF
     */
    if (self.REFCNT() == 1 && self->active()) {
        /* Not resurrected, but still not dead!
           XXX what else should we do? we complain. */
        PyObject* f = PySys_GetObject("stderr");
        Py_INCREF(self.borrow_o()); /* leak! */
        if (f != NULL) {
            PyFile_WriteString("GreenletExit did not kill ", f);
            PyFile_WriteObject(self.borrow_o(), f, 0);
            PyFile_WriteString("\n", f);
        }
    }
    /* Restore the saved exception. */
    saved_err.PyErrRestore();
    /* Undo the temporary resurrection; can't use DECREF here,
     * it would cause a recursive call.
     */
    assert(self.REFCNT() > 0);

    Py_ssize_t refcnt = self.REFCNT() - 1;
    Py_SET_REFCNT(self.borrow_o(), refcnt);
    if (refcnt != 0) {
        /* Resurrected! */
        _Py_NewReference(self.borrow_o());
        Py_SET_REFCNT(self.borrow_o(), refcnt);
        /* Better to use tp_finalizer slot (PEP 442)
         * and call ``PyObject_CallFinalizerFromDealloc``,
         * but that's only supported in Python 3.4+; see
         * Modules/_io/iobase.c for an example.
         *
         * The following approach is copied from iobase.c in CPython 2.7.
         * (along with much of this function in general). Here's their
         * comment:
         *
         * When called from a heap type's dealloc, the type will be
         * decref'ed on return (see e.g. subtype_dealloc in typeobject.c). */
        if (PyType_HasFeature(self.TYPE(), Py_TPFLAGS_HEAPTYPE)) {
            Py_INCREF(self.TYPE());
        }

        PyObject_GC_Track((PyObject*)self);

        _Py_DEC_REFTOTAL;
#ifdef COUNT_ALLOCS
        --Py_TYPE(self)->tp_frees;
        --Py_TYPE(self)->tp_allocs;
#endif /* COUNT_ALLOCS */
        return 0;
    }
    return 1;
}


static void
green_dealloc(PyGreenlet* self)
{
    PyObject_GC_UnTrack(self);
    BorrowedGreenlet me(self);
    if (me->active()
        && me->started()
        && !me->main()) {
        if (!_green_dealloc_kill_started_non_main_greenlet(me)) {
            return;
        }
    }

    if (self->weakreflist != NULL) {
        PyObject_ClearWeakRefs((PyObject*)self);
    }
    Py_CLEAR(self->dict);

    if (self->pimpl) {
        // In case deleting this, which frees some memory,
        // somehow winds up calling back into us. That's usually a
        //bug in our code.
        Greenlet* p = self->pimpl;
        self->pimpl = nullptr;
        delete p;
    }
    // and finally we're done. self is now invalid.
    Py_TYPE(self)->tp_free((PyObject*)self);
}



static OwnedObject
throw_greenlet(BorrowedGreenlet self, PyErrPieces& err_pieces)
{
    PyObject* result = nullptr;
    err_pieces.PyErrRestore();
    assert(PyErr_Occurred());
    if (self->started() && !self->active()) {
        /* dead greenlet: turn GreenletExit into a regular return */
        result = g_handle_exit(OwnedObject()).relinquish_ownership();
    }
    self->args() <<= result;

    return single_result(self->g_switch());
}



PyDoc_STRVAR(
    green_switch_doc,
    "switch(*args, **kwargs)\n"
    "\n"
    "Switch execution to this greenlet.\n"
    "\n"
    "If this greenlet has never been run, then this greenlet\n"
    "will be switched to using the body of ``self.run(*args, **kwargs)``.\n"
    "\n"
    "If the greenlet is active (has been run, but was switch()'ed\n"
    "out before leaving its run function), then this greenlet will\n"
    "be resumed and the return value to its switch call will be\n"
    "None if no arguments are given, the given argument if one\n"
    "argument is given, or the args tuple and keyword args dict if\n"
    "multiple arguments are given.\n"
    "\n"
    "If the greenlet is dead, or is the current greenlet then this\n"
    "function will simply return the arguments using the same rules as\n"
    "above.\n");

static PyObject*
green_switch(PyGreenlet* self, PyObject* args, PyObject* kwargs)
{
    using greenlet::SwitchingArgs;
    SwitchingArgs switch_args(OwnedObject::owning(args), OwnedObject::owning(kwargs));
    self->pimpl->may_switch_away();
    self->pimpl->args() <<= switch_args;

    // If we're switching out of a greenlet, and that switch is the
    // last thing the greenlet does, the greenlet ought to be able to
    // go ahead and die at that point. Currently, someone else must
    // manually switch back to the greenlet so that we "fall off the
    // end" and can perform cleanup. You'd think we'd be able to
    // figure out that this is happening using the frame's ``f_lasti``
    // member, which is supposed to be an index into
    // ``frame->f_code->co_code``, the bytecode string. However, in
    // recent interpreters, ``f_lasti`` tends not to be updated thanks
    // to things like the PREDICT() macros in ceval.c. So it doesn't
    // really work to do that in many cases. For example, the Python
    // code:
    //     def run():
    //         greenlet.getcurrent().parent.switch()
    // produces bytecode of len 16, with the actual call to switch()
    // being at index 10 (in Python 3.10). However, the reported
    // ``f_lasti`` we actually see is...5! (Which happens to be the
    // second byte of the CALL_METHOD op for ``getcurrent()``).

    try {
        //OwnedObject result = single_result(self->pimpl->g_switch());
        OwnedObject result(single_result(self->pimpl->g_switch()));
#ifndef NDEBUG
        // Note that the current greenlet isn't necessarily self. If self
        // finished, we went to one of its parents.
        assert(!self->pimpl->args());

        const BorrowedGreenlet& current = GET_THREAD_STATE().state().borrow_current();
        // It's possible it's never been switched to.
        assert(!current->args());
#endif
        PyObject* p = result.relinquish_ownership();

        if (!p && !PyErr_Occurred()) {
            // This shouldn't be happening anymore, so the asserts
            // are there for debug builds. Non-debug builds
            // crash "gracefully" in this case, although there is an
            // argument to be made for killing the process in all
            // cases --- for this to be the case, our switches
            // probably nested in an incorrect way, so the state is
            // suspicious. Nothing should be corrupt though, just
            // confused at the Python level. Letting this propagate is
            // probably good enough.
            assert(p || PyErr_Occurred());
            throw PyErrOccurred(
                mod_globs->PyExc_GreenletError,
                "Greenlet.switch() returned NULL without an exception set."
            );
        }
        return p;
    }
    catch(const PyErrOccurred&) {
        return nullptr;
    }
}

PyDoc_STRVAR(
    green_throw_doc,
    "Switches execution to this greenlet, but immediately raises the\n"
    "given exception in this greenlet.  If no argument is provided, the "
    "exception\n"
    "defaults to `greenlet.GreenletExit`.  The normal exception\n"
    "propagation rules apply, as described for `switch`.  Note that calling "
    "this\n"
    "method is almost equivalent to the following::\n"
    "\n"
    "    def raiser():\n"
    "        raise typ, val, tb\n"
    "    g_raiser = greenlet(raiser, parent=g)\n"
    "    g_raiser.switch()\n"
    "\n"
    "except that this trick does not work for the\n"
    "`greenlet.GreenletExit` exception, which would not propagate\n"
    "from ``g_raiser`` to ``g``.\n");

static PyObject*
green_throw(PyGreenlet* self, PyObject* args)
{
    PyArgParseParam typ(mod_globs->PyExc_GreenletExit);
    PyArgParseParam val;
    PyArgParseParam tb;

    if (!PyArg_ParseTuple(args, "|OOO:throw", &typ, &val, &tb)) {
        return nullptr;
    }

    assert(typ.borrow() || val.borrow());

    self->pimpl->may_switch_away();
    try {
        // Both normalizing the error and the actual throw_greenlet
        // could throw PyErrOccurred.
        PyErrPieces err_pieces(typ.borrow(), val.borrow(), tb.borrow());

        return throw_greenlet(self, err_pieces).relinquish_ownership();
    }
    catch (const PyErrOccurred&) {
        return nullptr;
    }
}

static int
green_bool(PyGreenlet* self)
{
    return self->pimpl->active();
}

/**
 * CAUTION: Allocates memory, may run GC and arbitrary Python code.
 */
static PyObject*
green_getdict(PyGreenlet* self, void* UNUSED(context))
{
    if (self->dict == NULL) {
        self->dict = PyDict_New();
        if (self->dict == NULL) {
            return NULL;
        }
    }
    Py_INCREF(self->dict);
    return self->dict;
}

static int
green_setdict(PyGreenlet* self, PyObject* val, void* UNUSED(context))
{
    PyObject* tmp;

    if (val == NULL) {
        PyErr_SetString(PyExc_TypeError, "__dict__ may not be deleted");
        return -1;
    }
    if (!PyDict_Check(val)) {
        PyErr_SetString(PyExc_TypeError, "__dict__ must be a dictionary");
        return -1;
    }
    tmp = self->dict;
    Py_INCREF(val);
    self->dict = val;
    Py_XDECREF(tmp);
    return 0;
}

static bool
_green_not_dead(BorrowedGreenlet self)
{
    // XXX: Where else should we do this?
    // Probably on entry to most Python-facing functions?
    if (self->was_running_in_dead_thread()) {
        self->deactivate_and_free();
        return false;
    }
    return self->active() || !self->started();
}


static PyObject*
green_getdead(BorrowedGreenlet self, void* UNUSED(context))
{
    if (_green_not_dead(self)) {
        Py_RETURN_FALSE;
    }
    else {
        Py_RETURN_TRUE;
    }
}

static PyObject*
green_get_stack_saved(PyGreenlet* self, void* UNUSED(context))
{
    return PyLong_FromSsize_t(self->pimpl->stack_saved());
}


static PyObject*
green_getrun(BorrowedGreenlet self, void* UNUSED(context))
{
    try {
        OwnedObject result(self->run());
        return result.relinquish_ownership();
    }
    catch(const PyErrOccurred&) {
        return nullptr;
    }
}





static int
green_setrun(BorrowedGreenlet self, BorrowedObject nrun, void* UNUSED(context))
{
    try {
        self->run(nrun);
        return 0;
    }
    catch(const PyErrOccurred&) {
        return -1;
    }
}

static PyObject*
green_getparent(BorrowedGreenlet self, void* UNUSED(context))
{
    return self->parent().acquire_or_None();
}



static int
green_setparent(BorrowedGreenlet self, BorrowedObject nparent, void* UNUSED(context))
{
    try {
        self->parent(nparent);
    }
    catch(const PyErrOccurred&) {
        return -1;
    }
    return 0;
}


static PyObject*
green_getcontext(const PyGreenlet* self, void* UNUSED(context))
{
    const Greenlet *const g = self->pimpl;
    try {
        OwnedObject result(g->context());
        return result.relinquish_ownership();
    }
    catch(const PyErrOccurred&) {
        return nullptr;
    }
}

static int
green_setcontext(BorrowedGreenlet self, PyObject* nctx, void* UNUSED(context))
{
    try {
        self->context(nctx);
        return 0;
    }
    catch(const PyErrOccurred&) {
        return -1;
    }
}


static PyObject*
green_getframe(BorrowedGreenlet self, void* UNUSED(context))
{
    const PythonState::OwnedFrame& top_frame = self->top_frame();
    return top_frame.acquire_or_None();
}

static PyObject*
green_getstate(PyGreenlet* self)
{
    PyErr_Format(PyExc_TypeError,
                 "cannot serialize '%s' object",
                 Py_TYPE(self)->tp_name);
    return nullptr;
}

static PyObject*
green_repr(BorrowedGreenlet self)
{
    /*
      Return a string like
      <greenlet.greenlet at 0xdeadbeef [current][active started]|dead main>

      The handling of greenlets across threads is not super good.
      We mostly use the internal definitions of these terms, but they
      generally should make sense to users as well.
     */
    PyObject* result;
    int never_started = !self->started() && !self->active();

    const char* const tp_name = Py_TYPE(self)->tp_name;

    if (_green_not_dead(self)) {
        /* XXX: The otid= is almost useless because you can't correlate it to
         any thread identifier exposed to Python. We could use
         PyThreadState_GET()->thread_id, but we'd need to save that in the
         greenlet, or save the whole PyThreadState object itself.

         As it stands, its only useful for identifying greenlets from the same thread.
        */
        const char* state_in_thread;
        if (self->was_running_in_dead_thread()) {
            // The thread it was running in is dead!
            // This can happen, especially at interpreter shut down.
            // It complicates debugging output because it may be
            // impossible to access the current thread state at that
            // time. Thus, don't access the current thread state.
            state_in_thread = " (thread exited)";
        }
        else {
            state_in_thread = GET_THREAD_STATE().state().is_current(self)
                ? " current"
                : (self->started() ? " suspended" : "");
        }
        result = PyUnicode_FromFormat(
            "<%s object at %p (otid=%p)%s%s%s%s>",
            tp_name,
            self.borrow_o(),
            self->thread_state(),
            state_in_thread,
            self->active() ? " active" : "",
            never_started ? " pending" : " started",
            self->main() ? " main" : ""
        );
    }
    else {
        result = PyUnicode_FromFormat(
            "<%s object at %p (otid=%p) %sdead>",
            tp_name,
            self.borrow_o(),
            self->thread_state(),
            self->was_running_in_dead_thread()
            ? "(thread exited) "
            : ""
            );
    }

    return result;
}

/*****************************************************************************
 * C interface
 *
 * These are exported using the CObject API
 */
extern "C" {
static PyGreenlet*
PyGreenlet_GetCurrent(void)
{
    return GET_THREAD_STATE().state().get_current().relinquish_ownership();
}

static int
PyGreenlet_SetParent(PyGreenlet* g, PyGreenlet* nparent)
{
    return green_setparent((PyGreenlet*)g, (PyObject*)nparent, NULL);
}

static PyGreenlet*
PyGreenlet_New(PyObject* run, PyGreenlet* parent)
{
    using greenlet::refs::NewDictReference;
    // In the past, we didn't use green_new and green_init, but that
    // was a maintenance issue because we duplicated code. This way is
    // much safer, but slightly slower. If that's a problem, we could
    // refactor green_init to separate argument parsing from initialization.
    OwnedGreenlet g = OwnedGreenlet::consuming(green_new(&PyGreenlet_Type, nullptr, nullptr));
    if (!g) {
        return NULL;
    }

    try {
        NewDictReference kwargs;
        if (run) {
            kwargs.SetItem(mod_globs->str_run, run);
        }
        if (parent) {
            kwargs.SetItem("parent", (PyObject*)parent);
        }

        Require(green_init(g, mod_globs->empty_tuple, kwargs));
    }
    catch (const PyErrOccurred&) {
        return nullptr;
    }

    return g.relinquish_ownership();
}

static PyObject*
PyGreenlet_Switch(PyGreenlet* self, PyObject* args, PyObject* kwargs)
{
    if (!PyGreenlet_Check(self)) {
        PyErr_BadArgument();
        return NULL;
    }

    if (args == NULL) {
        args = mod_globs->empty_tuple;
    }

    if (kwargs == NULL || !PyDict_Check(kwargs)) {
        kwargs = NULL;
    }

    return green_switch(self, args, kwargs);
}

static PyObject*
PyGreenlet_Throw(PyGreenlet* self, PyObject* typ, PyObject* val, PyObject* tb)
{
    if (!PyGreenlet_Check(self)) {
        PyErr_BadArgument();
        return nullptr;
    }
    try {
        PyErrPieces err_pieces(typ, val, tb);
        return throw_greenlet(self, err_pieces).relinquish_ownership();
    }
    catch (const PyErrOccurred&) {
        return nullptr;
    }
}

static int
Extern_PyGreenlet_MAIN(PyGreenlet* self)
{
    if (!PyGreenlet_Check(self)) {
        PyErr_BadArgument();
        return -1;
    }
    return self->pimpl->main();
}

static int
Extern_PyGreenlet_ACTIVE(PyGreenlet* self)
{
    if (!PyGreenlet_Check(self)) {
        PyErr_BadArgument();
        return -1;
    }
    return self->pimpl->active();
}

static int
Extern_PyGreenlet_STARTED(PyGreenlet* self)
{
    if (!PyGreenlet_Check(self)) {
        PyErr_BadArgument();
        return -1;
    }
    return self->pimpl->started();
}

static PyGreenlet*
Extern_PyGreenlet_GET_PARENT(PyGreenlet* self)
{
    if (!PyGreenlet_Check(self)) {
        PyErr_BadArgument();
        return NULL;
    }
    // This can return NULL even if there is no exception
    return self->pimpl->parent().acquire();
}
} // extern C.

/** End C API ****************************************************************/

static PyMethodDef green_methods[] = {
    {"switch",
     reinterpret_cast<PyCFunction>(green_switch),
     METH_VARARGS | METH_KEYWORDS,
     green_switch_doc},
    {"throw", (PyCFunction)green_throw, METH_VARARGS, green_throw_doc},
    {"__getstate__", (PyCFunction)green_getstate, METH_NOARGS, NULL},
    {NULL, NULL} /* sentinel */
};

static PyGetSetDef green_getsets[] = {
    /* name, getter, setter, doc, context pointer */
    {"__dict__", (getter)green_getdict, (setter)green_setdict, /*XXX*/ NULL},
    {"run", (getter)green_getrun, (setter)green_setrun, /*XXX*/ NULL},
    {"parent", (getter)green_getparent, (setter)green_setparent, /*XXX*/ NULL},
    {"gr_frame", (getter)green_getframe, NULL, /*XXX*/ NULL},
    {"gr_context",
     (getter)green_getcontext,
     (setter)green_setcontext,
     /*XXX*/ NULL},
    {"dead", (getter)green_getdead, NULL, /*XXX*/ NULL},
    {"_stack_saved", (getter)green_get_stack_saved, NULL, /*XXX*/ NULL},
    {NULL}
};

static PyMemberDef green_members[] = {
    {NULL}
};

static PyNumberMethods green_as_number = {
    NULL, /* nb_add */
    NULL, /* nb_subtract */
    NULL, /* nb_multiply */
    NULL,                /* nb_remainder */
    NULL,                /* nb_divmod */
    NULL,                /* nb_power */
    NULL,                /* nb_negative */
    NULL,                /* nb_positive */
    NULL,                /* nb_absolute */
    (inquiry)green_bool, /* nb_bool */
};


PyTypeObject PyGreenlet_Type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    "greenlet.greenlet", /* tp_name */
    sizeof(PyGreenlet),  /* tp_basicsize */
    0,                   /* tp_itemsize */
    /* methods */
    (destructor)green_dealloc, /* tp_dealloc */
    0,                         /* tp_print */
    0,                         /* tp_getattr */
    0,                         /* tp_setattr */
    0,                         /* tp_compare */
    (reprfunc)green_repr,      /* tp_repr */
    &green_as_number,          /* tp_as _number*/
    0,                         /* tp_as _sequence*/
    0,                         /* tp_as _mapping*/
    0,                         /* tp_hash */
    0,                         /* tp_call */
    0,                         /* tp_str */
    0,                         /* tp_getattro */
    0,                         /* tp_setattro */
    0,                         /* tp_as_buffer*/
    G_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE, /* tp_flags */
    "greenlet(run=None, parent=None) -> greenlet\n\n"
    "Creates a new greenlet object (without running it).\n\n"
    " - *run* -- The callable to invoke.\n"
    " - *parent* -- The parent greenlet. The default is the current "
    "greenlet.",                        /* tp_doc */
    (traverseproc)green_traverse, /* tp_traverse */
    (inquiry)green_clear,         /* tp_clear */
    0,                                  /* tp_richcompare */
    offsetof(PyGreenlet, weakreflist),  /* tp_weaklistoffset */
    0,                                  /* tp_iter */
    0,                                  /* tp_iternext */
    green_methods,                      /* tp_methods */
    green_members,                      /* tp_members */
    green_getsets,                      /* tp_getset */
    0,                                  /* tp_base */
    0,                                  /* tp_dict */
    0,                                  /* tp_descr_get */
    0,                                  /* tp_descr_set */
    offsetof(PyGreenlet, dict),         /* tp_dictoffset */
    (initproc)green_init,               /* tp_init */
    PyType_GenericAlloc,                  /* tp_alloc */
    (newfunc)green_new,                          /* tp_new */
    PyObject_GC_Del,                   /* tp_free */
    (inquiry)green_is_gc,         /* tp_is_gc */
};



static PyObject*
green_unswitchable_getforce(PyGreenlet* self, void* UNUSED(context))
{
    BrokenGreenlet* broken = dynamic_cast<BrokenGreenlet*>(self->pimpl);
    return PyBool_FromLong(broken->_force_switch_error);
}

static int
green_unswitchable_setforce(PyGreenlet* self, BorrowedObject nforce, void* UNUSED(context))
{
    if (!nforce) {
        PyErr_SetString(
            PyExc_AttributeError,
            "Cannot delete force_switch_error"
        );
        return -1;
    }
    BrokenGreenlet* broken = dynamic_cast<BrokenGreenlet*>(self->pimpl);
    int is_true = PyObject_IsTrue(nforce);
    if (is_true == -1) {
        return -1;
    }
    broken->_force_switch_error = is_true;
    return 0;
}

static PyObject*
green_unswitchable_getforceslp(PyGreenlet* self, void* UNUSED(context))
{
    BrokenGreenlet* broken = dynamic_cast<BrokenGreenlet*>(self->pimpl);
    return PyBool_FromLong(broken->_force_slp_switch_error);
}

static int
green_unswitchable_setforceslp(PyGreenlet* self, BorrowedObject nforce, void* UNUSED(context))
{
    if (!nforce) {
        PyErr_SetString(
            PyExc_AttributeError,
            "Cannot delete force_slp_switch_error"
        );
        return -1;
    }
    BrokenGreenlet* broken = dynamic_cast<BrokenGreenlet*>(self->pimpl);
    int is_true = PyObject_IsTrue(nforce);
    if (is_true == -1) {
        return -1;
    }
    broken->_force_slp_switch_error = is_true;
    return 0;
}

static PyGetSetDef green_unswitchable_getsets[] = {
    /* name, getter, setter, doc, context pointer */
    {"force_switch_error",
     (getter)green_unswitchable_getforce,
     (setter)green_unswitchable_setforce,
     /*XXX*/ NULL},
    {"force_slp_switch_error",
     (getter)green_unswitchable_getforceslp,
     (setter)green_unswitchable_setforceslp,
     /*XXX*/ NULL},

    {NULL}
};

PyTypeObject PyGreenletUnswitchable_Type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    "greenlet._greenlet.UnswitchableGreenlet",
    0,  /* tp_basicsize */
    0,                   /* tp_itemsize */
    /* methods */
    (destructor)green_dealloc, /* tp_dealloc */
    0,                         /* tp_print */
    0,                         /* tp_getattr */
    0,                         /* tp_setattr */
    0,                         /* tp_compare */
    0,      /* tp_repr */
    0,          /* tp_as _number*/
    0,                         /* tp_as _sequence*/
    0,                         /* tp_as _mapping*/
    0,                         /* tp_hash */
    0,                         /* tp_call */
    0,                         /* tp_str */
    0,                         /* tp_getattro */
    0,                         /* tp_setattro */
    0,                         /* tp_as_buffer*/
    G_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE, /* tp_flags */
    "Undocumented internal class",                        /* tp_doc */
    (traverseproc)green_traverse, /* tp_traverse */
    (inquiry)green_clear,         /* tp_clear */
    0,                                  /* tp_richcompare */
    0,  /* tp_weaklistoffset */
    0,                                  /* tp_iter */
    0,                                  /* tp_iternext */
    0,                      /* tp_methods */
    0,                      /* tp_members */
    green_unswitchable_getsets,                      /* tp_getset */
    &PyGreenlet_Type,                                  /* tp_base */
    0,                                  /* tp_dict */
    0,                                  /* tp_descr_get */
    0,                                  /* tp_descr_set */
    0,         /* tp_dictoffset */
    (initproc)green_init,               /* tp_init */
    PyType_GenericAlloc,                  /* tp_alloc */
    (newfunc)green_unswitchable_new,                          /* tp_new */
    PyObject_GC_Del,                   /* tp_free */
    (inquiry)green_is_gc,         /* tp_is_gc */
};


PyDoc_STRVAR(mod_getcurrent_doc,
             "getcurrent() -> greenlet\n"
             "\n"
             "Returns the current greenlet (i.e. the one which called this "
             "function).\n");

static PyObject*
mod_getcurrent(PyObject* UNUSED(module))
{
    return GET_THREAD_STATE().state().get_current().relinquish_ownership_o();
}

PyDoc_STRVAR(mod_settrace_doc,
             "settrace(callback) -> object\n"
             "\n"
             "Sets a new tracing function and returns the previous one.\n");
static PyObject*
mod_settrace(PyObject* UNUSED(module), PyObject* args)
{
    PyArgParseParam tracefunc;
    if (!PyArg_ParseTuple(args, "O", &tracefunc)) {
        return NULL;
    }
    ThreadState& state = GET_THREAD_STATE();
    OwnedObject previous = state.get_tracefunc();
    if (!previous) {
        previous = Py_None;
    }

    state.set_tracefunc(tracefunc);

    return previous.relinquish_ownership();
}

PyDoc_STRVAR(mod_gettrace_doc,
             "gettrace() -> object\n"
             "\n"
             "Returns the currently set tracing function, or None.\n");

static PyObject*
mod_gettrace(PyObject* UNUSED(module))
{
    OwnedObject tracefunc = GET_THREAD_STATE().state().get_tracefunc();
    if (!tracefunc) {
        tracefunc = Py_None;
    }
    return tracefunc.relinquish_ownership();
}

PyDoc_STRVAR(mod_set_thread_local_doc,
             "set_thread_local(key, value) -> None\n"
             "\n"
             "Set a value in the current thread-local dictionary. Debbuging only.\n");

static PyObject*
mod_set_thread_local(PyObject* UNUSED(module), PyObject* args)
{
    PyArgParseParam key;
    PyArgParseParam value;
    PyObject* result = NULL;

    if (PyArg_UnpackTuple(args, "set_thread_local", 2, 2, &key, &value)) {
        if(PyDict_SetItem(
                          PyThreadState_GetDict(), // borrow
                          key,
                          value) == 0 ) {
            // success
            Py_INCREF(Py_None);
            result = Py_None;
        }
    }
    return result;
}

PyDoc_STRVAR(mod_get_pending_cleanup_count_doc,
             "get_pending_cleanup_count() -> Integer\n"
             "\n"
             "Get the number of greenlet cleanup operations pending. Testing only.\n");


static PyObject*
mod_get_pending_cleanup_count(PyObject* UNUSED(module))
{
    LockGuard cleanup_lock(*mod_globs->thread_states_to_destroy_lock);
    return PyLong_FromSize_t(mod_globs->thread_states_to_destroy.size());
}

PyDoc_STRVAR(mod_get_total_main_greenlets_doc,
             "get_total_main_greenlets() -> Integer\n"
             "\n"
             "Quickly return the number of main greenlets that exist. Testing only.\n");

static PyObject*
mod_get_total_main_greenlets(PyObject* UNUSED(module))
{
    return PyLong_FromSize_t(G_TOTAL_MAIN_GREENLETS);
}

PyDoc_STRVAR(mod_get_clocks_used_doing_optional_cleanup_doc,
             "get_clocks_used_doing_optional_cleanup() -> Integer\n"
             "\n"
             "Get the number of clock ticks the program has used doing optional "
             "greenlet cleanup.\n"
             "Beginning in greenlet 2.0, greenlet tries to find and dispose of greenlets\n"
             "that leaked after a thread exited. This requires invoking Python's garbage collector,\n"
             "which may have a performance cost proportional to the number of live objects.\n"
             "This function returns the amount of processor time\n"
             "greenlet has used to do this. In programs that run with very large amounts of live\n"
             "objects, this metric can be used to decide whether the cost of doing this cleanup\n"
             "is worth the memory leak being corrected. If not, you can disable the cleanup\n"
             "using ``enable_optional_cleanup(False)``.\n"
             "The units are arbitrary and can only be compared to themselves (similarly to ``time.clock()``);\n"
             "for example, to see how it scales with your heap. You can attempt to convert them into seconds\n"
             "by dividing by the value of CLOCKS_PER_SEC."
             "If cleanup has been disabled, returns None."
             "\n"
             "This is an implementation specific, provisional API. It may be changed or removed\n"
             "in the future.\n"
             ".. versionadded:: 2.0"
             );
static PyObject*
mod_get_clocks_used_doing_optional_cleanup(PyObject* UNUSED(module))
{
    std::clock_t& clocks = ThreadState::clocks_used_doing_gc();

    if (clocks == std::clock_t(-1)) {
        Py_RETURN_NONE;
    }
    // This might not actually work on some implementations; clock_t
    // is an opaque type.
    return PyLong_FromSsize_t(clocks);
}

PyDoc_STRVAR(mod_enable_optional_cleanup_doc,
             "mod_enable_optional_cleanup(bool) -> None\n"
             "\n"
             "Enable or disable optional cleanup operations.\n"
             "See ``get_clocks_used_doing_optional_cleanup()`` for details.\n"
             );
static PyObject*
mod_enable_optional_cleanup(PyObject* UNUSED(module), PyObject* flag)
{
    int is_true = PyObject_IsTrue(flag);
    if (is_true == -1) {
        return nullptr;
    }

    std::clock_t& clocks = ThreadState::clocks_used_doing_gc();
    if (is_true) {
        // If we already have a value, we don't want to lose it.
        if (clocks == std::clock_t(-1)) {
            clocks = 0;
        }
    }
    else {
        clocks = std::clock_t(-1);
    }
    Py_RETURN_NONE;
}

PyDoc_STRVAR(mod_get_tstate_trash_delete_nesting_doc,
             "get_tstate_trash_delete_nesting() -> Integer\n"
             "\n"
             "Return the 'trash can' nesting level. Testing only.\n");
static PyObject*
mod_get_tstate_trash_delete_nesting(PyObject* UNUSED(module))
{
    PyThreadState* tstate = PyThreadState_GET();

#if GREENLET_PY312
    return PyLong_FromLong(tstate->trash.delete_nesting);
#else
    return PyLong_FromLong(tstate->trash_delete_nesting);
#endif
}

static PyMethodDef GreenMethods[] = {
    {"getcurrent",
     (PyCFunction)mod_getcurrent,
     METH_NOARGS,
     mod_getcurrent_doc},
    {"settrace", (PyCFunction)mod_settrace, METH_VARARGS, mod_settrace_doc},
    {"gettrace", (PyCFunction)mod_gettrace, METH_NOARGS, mod_gettrace_doc},
    {"set_thread_local", (PyCFunction)mod_set_thread_local, METH_VARARGS, mod_set_thread_local_doc},
    {"get_pending_cleanup_count", (PyCFunction)mod_get_pending_cleanup_count, METH_NOARGS, mod_get_pending_cleanup_count_doc},
    {"get_total_main_greenlets", (PyCFunction)mod_get_total_main_greenlets, METH_NOARGS, mod_get_total_main_greenlets_doc},
    {"get_clocks_used_doing_optional_cleanup", (PyCFunction)mod_get_clocks_used_doing_optional_cleanup, METH_NOARGS, mod_get_clocks_used_doing_optional_cleanup_doc},
    {"enable_optional_cleanup", (PyCFunction)mod_enable_optional_cleanup, METH_O, mod_enable_optional_cleanup_doc},
    {"get_tstate_trash_delete_nesting", (PyCFunction)mod_get_tstate_trash_delete_nesting, METH_NOARGS, mod_get_tstate_trash_delete_nesting_doc},
    {NULL, NULL} /* Sentinel */
};

static const char* const copy_on_greentype[] = {
    "getcurrent",
    "error",
    "GreenletExit",
    "settrace",
    "gettrace",
    NULL
};

static struct PyModuleDef greenlet_module_def = {
    PyModuleDef_HEAD_INIT,
    "greenlet._greenlet",
    NULL,
    -1,
    GreenMethods,
};



static PyObject*
greenlet_internal_mod_init() noexcept
{
    static void* _PyGreenlet_API[PyGreenlet_API_pointers];

    try {
        CreatedModule m(greenlet_module_def);

        Require(PyType_Ready(&PyGreenlet_Type));
        Require(PyType_Ready(&PyGreenletUnswitchable_Type));

        mod_globs = new greenlet::GreenletGlobals;
        ThreadState::init();

        m.PyAddObject("greenlet", PyGreenlet_Type);
        m.PyAddObject("UnswitchableGreenlet", PyGreenletUnswitchable_Type);
        m.PyAddObject("error", mod_globs->PyExc_GreenletError);
        m.PyAddObject("GreenletExit", mod_globs->PyExc_GreenletExit);

        m.PyAddObject("GREENLET_USE_GC", 1);
        m.PyAddObject("GREENLET_USE_TRACING", 1);
        m.PyAddObject("GREENLET_USE_CONTEXT_VARS", 1L);
        m.PyAddObject("GREENLET_USE_STANDARD_THREADING", 1L);

        OwnedObject clocks_per_sec = OwnedObject::consuming(PyLong_FromSsize_t(CLOCKS_PER_SEC));
        m.PyAddObject("CLOCKS_PER_SEC", clocks_per_sec);

        /* also publish module-level data as attributes of the greentype. */
        // XXX: This is weird, and enables a strange pattern of
        // confusing the class greenlet with the module greenlet; with
        // the exception of (possibly) ``getcurrent()``, this
        // shouldn't be encouraged so don't add new items here.
        for (const char* const* p = copy_on_greentype; *p; p++) {
            OwnedObject o = m.PyRequireAttr(*p);
            PyDict_SetItemString(PyGreenlet_Type.tp_dict, *p, o.borrow());
        }

        /*
         * Expose C API
         */

        /* types */
        _PyGreenlet_API[PyGreenlet_Type_NUM] = (void*)&PyGreenlet_Type;

        /* exceptions */
        _PyGreenlet_API[PyExc_GreenletError_NUM] = (void*)mod_globs->PyExc_GreenletError;
        _PyGreenlet_API[PyExc_GreenletExit_NUM] = (void*)mod_globs->PyExc_GreenletExit;

        /* methods */
        _PyGreenlet_API[PyGreenlet_New_NUM] = (void*)PyGreenlet_New;
        _PyGreenlet_API[PyGreenlet_GetCurrent_NUM] = (void*)PyGreenlet_GetCurrent;
        _PyGreenlet_API[PyGreenlet_Throw_NUM] = (void*)PyGreenlet_Throw;
        _PyGreenlet_API[PyGreenlet_Switch_NUM] = (void*)PyGreenlet_Switch;
        _PyGreenlet_API[PyGreenlet_SetParent_NUM] = (void*)PyGreenlet_SetParent;

        /* Previously macros, but now need to be functions externally. */
        _PyGreenlet_API[PyGreenlet_MAIN_NUM] = (void*)Extern_PyGreenlet_MAIN;
        _PyGreenlet_API[PyGreenlet_STARTED_NUM] = (void*)Extern_PyGreenlet_STARTED;
        _PyGreenlet_API[PyGreenlet_ACTIVE_NUM] = (void*)Extern_PyGreenlet_ACTIVE;
        _PyGreenlet_API[PyGreenlet_GET_PARENT_NUM] = (void*)Extern_PyGreenlet_GET_PARENT;

        /* XXX: Note that our module name is ``greenlet._greenlet``, but for
           backwards compatibility with existing C code, we need the _C_API to
           be directly in greenlet.
        */
        const NewReference c_api_object(Require(
                                           PyCapsule_New(
                                               (void*)_PyGreenlet_API,
                                               "greenlet._C_API",
                                               NULL)));
        m.PyAddObject("_C_API", c_api_object);
        assert(c_api_object.REFCNT() == 2);

        // cerr << "Sizes:"
        //      << "\n\tGreenlet       : " << sizeof(Greenlet)
        //      << "\n\tUserGreenlet   : " << sizeof(UserGreenlet)
        //      << "\n\tMainGreenlet   : " << sizeof(MainGreenlet)
        //      << "\n\tExceptionState : " << sizeof(greenlet::ExceptionState)
        //      << "\n\tPythonState    : " << sizeof(greenlet::PythonState)
        //      << "\n\tStackState     : " << sizeof(greenlet::StackState)
        //      << "\n\tSwitchingArgs  : " << sizeof(greenlet::SwitchingArgs)
        //      << "\n\tOwnedObject    : " << sizeof(greenlet::refs::OwnedObject)
        //      << "\n\tBorrowedObject : " << sizeof(greenlet::refs::BorrowedObject)
        //      << "\n\tPyGreenlet     : " << sizeof(PyGreenlet)
        //      << endl;

        return m.borrow(); // But really it's the main reference.
    }
    catch (const LockInitError& e) {
        PyErr_SetString(PyExc_MemoryError, e.what());
        return NULL;
    }
    catch (const PyErrOccurred&) {
        return NULL;
    }

}

extern "C" {

PyMODINIT_FUNC
PyInit__greenlet(void)
{
    return greenlet_internal_mod_init();
}

}; // extern C

#ifdef __clang__
#    pragma clang diagnostic pop
#elif defined(__GNUC__)
#    pragma GCC diagnostic pop
#endif
