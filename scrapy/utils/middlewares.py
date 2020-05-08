# coding: utf-8
import inspect


def process_normal_iterable_helper(it, in_predicate=None, out_predicate=None, processor=None):
    for o in it:
        if in_predicate and not in_predicate(o):
            continue
        if processor is not None:
            o = processor(o)
        if out_predicate and not out_predicate(o):
            continue
        yield o


def process_iterable_helper(it, in_predicate=None, out_predicate=None, processor=None):
    """
    For each item in the iterable: skips it if in_predicate is False, applies processor,
    skips the result if out_predicate is False, else yields it.
    """
    if hasattr(inspect, 'isasyncgen') and inspect.isasyncgen(it):
        from scrapy.utils.asyncgen import process_async_iterable_helper  # Python 3.5 limitation
        return process_async_iterable_helper(it, in_predicate, out_predicate, processor)
    else:
        return process_normal_iterable_helper(it, in_predicate, out_predicate, processor)
