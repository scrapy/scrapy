from collections.abc import AsyncIterable


async def collect_asyncgen(result: AsyncIterable):
    results = []
    async for x in result:
        results.append(x)
    return results
