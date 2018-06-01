import inspect


def get_args(method_or_func):
    """Returns method or function arguments."""
    try:
        # Python 3.0+
        args = list(inspect.signature(method_or_func).parameters.keys())
    except AttributeError:
        # Python 2.7
        args = inspect.getargspec(method_or_func).args
    return args
