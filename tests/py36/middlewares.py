async def RequestInOrderMiddleware_process_start_requests(f, start_requests, spider):
    async for r in start_requests or ():
        yield f(r, spider)
