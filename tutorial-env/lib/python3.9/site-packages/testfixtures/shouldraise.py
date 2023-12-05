from contextlib import contextmanager
from functools import wraps
from typing import Union, Type, Callable

from testfixtures import diff, compare

ExceptionOrType = Union[Exception, Type[Exception]]


param_docs = """

    :param exception: This can be one of the following:

                      * `None`, indicating that an exception must be
                        raised, but the type is unimportant.

                      * An exception class, indicating that the type
                        of the exception is important but not the
                        parameters it is created with.

                      * An exception instance, indicating that an
                        exception exactly matching the one supplied
                        should be raised.

    :param unless: Can be passed a boolean that, when ``True`` indicates that
                   no exception is expected. This is useful when checking
                   that exceptions are only raised on certain versions of
                   Python.
"""


class ShouldRaise(object):
    __doc__ = """
    This context manager is used to assert that an exception is raised
    within the context it is managing.
    """ + param_docs

    #: The exception captured by the context manager.
    #: Can be used to inspect specific attributes of the exception.
    raised = None

    def __init__(self, exception: ExceptionOrType = None, unless: bool = False):
        self.exception = exception
        self.expected = not unless

    def __enter__(self):
        return self

    def __exit__(self, type_, actual, traceback):
        __tracebackhide__ = True
        self.raised = actual
        if self.expected:
            if self.exception:
                if actual is not None:
                    if isinstance(self.exception, type):
                        actual = type(actual)
                        if self.exception is not actual:
                            return False
                    else:
                        if type(self.exception) is not type(actual):
                            return False
                compare(self.exception,
                        actual,
                        x_label='expected',
                        y_label='raised')
            elif not actual:
                raise AssertionError('No exception raised!')
        elif actual:
            return False
        return True


class should_raise:
    __doc__ = """
    A decorator to assert that the decorated function will raised
    an exception. An exception class or exception instance may be
    passed to check more specifically exactly what exception will be
    raised.
    """ + param_docs

    def __init__(self, exception: ExceptionOrType = None, unless: bool = None):
        self.exception = exception
        self.unless = unless

    def __call__(self, target: Callable) -> Callable:

        @wraps(target)
        def _should_raise_wrapper(*args, **kw):
            with ShouldRaise(self.exception, self.unless):
                target(*args, **kw)

        return _should_raise_wrapper


@contextmanager
def ShouldAssert(expected_text: str):
    """
    A context manager to check that an :class:`AssertionError`
    is raised and its text is as expected.
    """
    try:
        yield
    except AssertionError as e:
        actual_text = str(e)
        if expected_text != actual_text:
            raise AssertionError(diff(expected_text, actual_text,
                                      x_label='expected', y_label='actual'))
    else:
        raise AssertionError('Expected AssertionError(%r), None raised!' %
                             expected_text)
