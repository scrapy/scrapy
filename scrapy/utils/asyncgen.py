import functools
import inspect
from typing import AsyncGenerator, AsyncIterable, Callable, Generator, Iterable, Union


async def collect_asyncgen(result: AsyncIterable):
    results = []
    async for x in result:
        results.append(x)
    return results


async def as_async_generator(it: Union[Iterable, AsyncIterable]) -> AsyncGenerator:
    """ Wraps an iterable (sync or async) into an async generator. """
    if isinstance(it, AsyncIterable):
        async for r in it:
            yield r
    else:
        for r in it:
            yield r


# https://stackoverflow.com/a/66170760/113586
def _process_iterable_universal(process_async: Callable):
    """ Takes a function that takes an async iterable, args and kwargs. Returns
    a function that takes any iterable, args and kwargs.

    Requires that process_async only awaits on the iterable and synchronous functions,
    so it's better to use this only in the Scrapy code itself.
    """

    # If this stops working, all internal uses can be just replaced with manually-written
    # process_sync functions.

    def process_sync(iterable: Iterable, *args, **kwargs) -> Generator:
        agen = process_async(as_async_generator(iterable), *args, **kwargs)
        if not inspect.isasyncgen(agen):
            raise ValueError(f"process_async returned wrong type {type(agen)}")
        sent = None
        while True:
            try:
                gen = agen.asend(sent)
                gen.send(None)
            except StopIteration as e:
                sent = yield e.value
            except StopAsyncIteration:
                return
            else:
                gen.throw(RuntimeError,
                          f"Synchronously-called function '{process_async.__name__}' has blocked, "
                          f"you can't use {_process_iterable_universal.__name__} with it.")

    @functools.wraps(process_async)
    def process(iterable: Union[Iterable, AsyncIterable], *args, **kwargs) -> Union[Generator, AsyncGenerator]:
        if isinstance(iterable, AsyncIterable):
            # call process_async directly
            return process_async(iterable, *args, **kwargs)
        if isinstance(iterable, Iterable):
            # convert process_async to process_sync
            return process_sync(iterable, *args, **kwargs)
        raise TypeError(f"Wrong iterable type {type(iterable)}")

    return process
