import warnings


def send_catch_log(*args, **kwargs):
    warnings.warn(
        "The `scrapy.utils.signal` module is deprecated and will be removed in a future release. "
        "Please use `scrapy.utils.signal_ops` instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    from .signal_ops import send_catch_log

    return send_catch_log(*args, **kwargs)


def send_catch_log_deferred(*args, **kwargs):
    warnings.warn(
        "The `scrapy.utils.signal` module is deprecated and will be removed in a future release. "
        "Please use `scrapy.utils.signal_ops` instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    from .signal_ops import send_catch_log_deferred

    return send_catch_log_deferred(*args, **kwargs)


def disconnect_all(*args, **kwargs):
    warnings.warn(
        "The `scrapy.utils.signal` module is deprecated and will be removed in a future release. "
        "Please use `scrapy.utils.signal_ops` instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    from .signal_ops import disconnect_all

    return disconnect_all(*args, **kwargs)
