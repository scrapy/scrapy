"""
Call loop machinery
"""
from __future__ import annotations

from typing import cast
from typing import Generator
from typing import Mapping
from typing import Sequence
from typing import Tuple
from typing import Union

from ._hooks import HookImpl
from ._result import _raise_wrapfail
from ._result import HookCallError
from ._result import Result


# Need to distinguish between old- and new-style hook wrappers.
# Wrapping one a singleton tuple is the fastest type-safe way I found to do it.
Teardown = Union[
    Tuple[Generator[None, Result[object], None]],
    Generator[None, object, object],
]


def _multicall(
    hook_name: str,
    hook_impls: Sequence[HookImpl],
    caller_kwargs: Mapping[str, object],
    firstresult: bool,
) -> object | list[object]:
    """Execute a call into multiple python functions/methods and return the
    result(s).

    ``caller_kwargs`` comes from HookCaller.__call__().
    """
    __tracebackhide__ = True
    results: list[object] = []
    exception = None
    only_new_style_wrappers = True
    try:  # run impl and wrapper setup functions in a loop
        teardowns: list[Teardown] = []
        try:
            for hook_impl in reversed(hook_impls):
                try:
                    args = [caller_kwargs[argname] for argname in hook_impl.argnames]
                except KeyError:
                    for argname in hook_impl.argnames:
                        if argname not in caller_kwargs:
                            raise HookCallError(
                                f"hook call must provide argument {argname!r}"
                            )

                if hook_impl.hookwrapper:
                    only_new_style_wrappers = False
                    try:
                        # If this cast is not valid, a type error is raised below,
                        # which is the desired response.
                        res = hook_impl.function(*args)
                        wrapper_gen = cast(Generator[None, Result[object], None], res)
                        next(wrapper_gen)  # first yield
                        teardowns.append((wrapper_gen,))
                    except StopIteration:
                        _raise_wrapfail(wrapper_gen, "did not yield")
                elif hook_impl.wrapper:
                    try:
                        # If this cast is not valid, a type error is raised below,
                        # which is the desired response.
                        res = hook_impl.function(*args)
                        function_gen = cast(Generator[None, object, object], res)
                        next(function_gen)  # first yield
                        teardowns.append(function_gen)
                    except StopIteration:
                        _raise_wrapfail(function_gen, "did not yield")
                else:
                    res = hook_impl.function(*args)
                    if res is not None:
                        results.append(res)
                        if firstresult:  # halt further impl calls
                            break
        except BaseException as exc:
            exception = exc
    finally:
        # Fast path - only new-style wrappers, no Result.
        if only_new_style_wrappers:
            if firstresult:  # first result hooks return a single value
                result = results[0] if results else None
            else:
                result = results

            # run all wrapper post-yield blocks
            for teardown in reversed(teardowns):
                try:
                    if exception is not None:
                        teardown.throw(exception)  # type: ignore[union-attr]
                    else:
                        teardown.send(result)  # type: ignore[union-attr]
                    # Following is unreachable for a well behaved hook wrapper.
                    # Try to force finalizers otherwise postponed till GC action.
                    # Note: close() may raise if generator handles GeneratorExit.
                    teardown.close()  # type: ignore[union-attr]
                except StopIteration as si:
                    result = si.value
                    exception = None
                    continue
                except BaseException as e:
                    exception = e
                    continue
                _raise_wrapfail(teardown, "has second yield")  # type: ignore[arg-type]

            if exception is not None:
                raise exception.with_traceback(exception.__traceback__)
            else:
                return result

        # Slow path - need to support old-style wrappers.
        else:
            if firstresult:  # first result hooks return a single value
                outcome: Result[object | list[object]] = Result(
                    results[0] if results else None, exception
                )
            else:
                outcome = Result(results, exception)

            # run all wrapper post-yield blocks
            for teardown in reversed(teardowns):
                if isinstance(teardown, tuple):
                    try:
                        teardown[0].send(outcome)
                        _raise_wrapfail(teardown[0], "has second yield")
                    except StopIteration:
                        pass
                else:
                    try:
                        if outcome._exception is not None:
                            teardown.throw(outcome._exception)
                        else:
                            teardown.send(outcome._result)
                        # Following is unreachable for a well behaved hook wrapper.
                        # Try to force finalizers otherwise postponed till GC action.
                        # Note: close() may raise if generator handles GeneratorExit.
                        teardown.close()
                    except StopIteration as si:
                        outcome.force_result(si.value)
                        continue
                    except BaseException as e:
                        outcome.force_exception(e)
                        continue
                    _raise_wrapfail(teardown, "has second yield")

            return outcome.get_result()
