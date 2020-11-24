async def collect_asyncgen(result):
    results = []
    async for x in result:
        results.append(x)
    return results
