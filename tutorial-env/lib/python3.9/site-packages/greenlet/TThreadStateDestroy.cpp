/* -*- indent-tabs-mode: nil; tab-width: 4; -*- */
/**
 * Implementation of the ThreadState destructors.
 *
 * Format with:
 *  clang-format -i --style=file src/greenlet/greenlet.c
 *
 *
 * Fix missing braces with:
 *   clang-tidy src/greenlet/greenlet.c -fix -checks="readability-braces-around-statements"
*/
#ifndef T_THREADSTATE_DESTROY
#define T_THREADSTATE_DESTROY

#include "greenlet_greenlet.hpp"
#include "greenlet_thread_state.hpp"
#include "greenlet_thread_support.hpp"
#include "greenlet_cpython_add_pending.hpp"
#include "TGreenletGlobals.cpp"

namespace greenlet {

struct ThreadState_DestroyWithGIL
{
    ThreadState_DestroyWithGIL(ThreadState* state)
    {
        if (state && state->has_main_greenlet()) {
            DestroyWithGIL(state);
        }
    }

    static int
    DestroyWithGIL(ThreadState* state)
    {
        // Holding the GIL.
        // Passed a non-shared pointer to the actual thread state.
        // state -> main greenlet
        assert(state->has_main_greenlet());
        PyGreenlet* main(state->borrow_main_greenlet());
        // When we need to do cross-thread operations, we check this.
        // A NULL value means the thread died some time ago.
        // We do this here, rather than in a Python dealloc function
        // for the greenlet, in case there's still a reference out
        // there.
        static_cast<MainGreenlet*>(main->pimpl)->thread_state(nullptr);

        delete state; // Deleting this runs the destructor, DECREFs the main greenlet.
        return 0;
    }
};



struct ThreadState_DestroyNoGIL
{
    // ensure this is actually defined.
    static_assert(GREENLET_BROKEN_PY_ADD_PENDING == 1 || GREENLET_BROKEN_PY_ADD_PENDING == 0,
                  "GREENLET_BROKEN_PY_ADD_PENDING not defined correctly.");

#if GREENLET_BROKEN_PY_ADD_PENDING
    static int _push_pending_call(struct _pending_calls *pending,
                                  int (*func)(void *), void *arg)
    {
        int i = pending->last;
        int j = (i + 1) % NPENDINGCALLS;
        if (j == pending->first) {
            return -1; /* Queue full */
        }
        pending->calls[i].func = func;
        pending->calls[i].arg = arg;
        pending->last = j;
        return 0;
    }

    static int AddPendingCall(int (*func)(void *), void *arg)
    {
        _PyRuntimeState *runtime = &_PyRuntime;
        if (!runtime) {
            // obviously impossible
            return 0;
        }
        struct _pending_calls *pending = &runtime->ceval.pending;
        if (!pending->lock) {
            return 0;
        }
        int result = 0;
        PyThread_acquire_lock(pending->lock, WAIT_LOCK);
        if (!pending->finishing) {
            result = _push_pending_call(pending, func, arg);
        }
        PyThread_release_lock(pending->lock);
        SIGNAL_PENDING_CALLS(&runtime->ceval);
        return result;
    }
#else
    // Python < 3.8 or >= 3.9
    static int AddPendingCall(int (*func)(void*), void* arg)
    {
        return Py_AddPendingCall(func, arg);
    }
#endif

    ThreadState_DestroyNoGIL(ThreadState* state)
    {
        // We are *NOT* holding the GIL. Our thread is in the middle
        // of its death throes and the Python thread state is already
        // gone so we can't use most Python APIs. One that is safe is
        // ``Py_AddPendingCall``, unless the interpreter itself has
        // been torn down. There is a limited number of calls that can
        // be queued: 32 (NPENDINGCALLS) in CPython 3.10, so we
        // coalesce these calls using our own queue.
        if (state && state->has_main_greenlet()) {
            // mark the thread as dead ASAP.
            // this is racy! If we try to throw or switch to a
            // greenlet from this thread from some other thread before
            // we clear the state pointer, it won't realize the state
            // is dead which can crash the process.
            PyGreenlet* p = state->borrow_main_greenlet();
            assert(p->pimpl->thread_state() == state || p->pimpl->thread_state() == nullptr);
            static_cast<MainGreenlet*>(p->pimpl)->thread_state(nullptr);
        }

        // NOTE: Because we're not holding the GIL here, some other
        // Python thread could run and call ``os.fork()``, which would
        // be bad if that happenend while we are holding the cleanup
        // lock (it wouldn't function in the child process).
        // Make a best effort to try to keep the duration we hold the
        // lock short.
        // TODO: On platforms that support it, use ``pthread_atfork`` to
        // drop this lock.
        LockGuard cleanup_lock(*mod_globs->thread_states_to_destroy_lock);

        if (state && state->has_main_greenlet()) {
            // Because we don't have the GIL, this is a race condition.
            if (!PyInterpreterState_Head()) {
                // We have to leak the thread state, if the
                // interpreter has shut down when we're getting
                // deallocated, we can't run the cleanup code that
                // deleting it would imply.
                return;
            }

            mod_globs->queue_to_destroy(state);
            if (mod_globs->thread_states_to_destroy.size() == 1) {
                // We added the first item to the queue. We need to schedule
                // the cleanup.
                int result = ThreadState_DestroyNoGIL::AddPendingCall(
                    ThreadState_DestroyNoGIL::DestroyQueueWithGIL,
                    NULL);
                if (result < 0) {
                    // Hmm, what can we do here?
                    fprintf(stderr,
                            "greenlet: WARNING: failed in call to Py_AddPendingCall; "
                            "expect a memory leak.\n");
                }
            }
        }
    }

    static int
    DestroyQueueWithGIL(void* UNUSED(arg))
    {
        // We're holding the GIL here, so no Python code should be able to
        // run to call ``os.fork()``.
        while (1) {
            ThreadState* to_destroy;
            {
                LockGuard cleanup_lock(*mod_globs->thread_states_to_destroy_lock);
                if (mod_globs->thread_states_to_destroy.empty()) {
                    break;
                }
                to_destroy = mod_globs->take_next_to_destroy();
            }
            // Drop the lock while we do the actual deletion.
            ThreadState_DestroyWithGIL::DestroyWithGIL(to_destroy);
        }
        return 0;
    }

};

}; // namespace greenlet

// The intent when GET_THREAD_STATE() is needed multiple times in a
// function is to take a reference to its return value in a local
// variable, to avoid the thread-local indirection. On some platforms
// (macOS), accessing a thread-local involves a function call (plus an
// initial function call in each function that uses a thread local);
// in contrast, static volatile variables are at some pre-computed
// offset.
typedef greenlet::ThreadStateCreator<greenlet::ThreadState_DestroyNoGIL> ThreadStateCreator;
static thread_local ThreadStateCreator g_thread_state_global;
#define GET_THREAD_STATE() g_thread_state_global

#endif //T_THREADSTATE_DESTROY
