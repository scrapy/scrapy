def RequestInOrderMiddleware_process_start_requests(f, start_requests, spider):
    return (f(r, spider) async for r in start_requests or ())
