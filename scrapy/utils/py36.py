"""
Helpers using Python 3.6+ syntax (ignore SyntaxError on import).
"""


async def collect_asyncgen(result):
    results = []
    async for x in result:
        results.append(x)
    return results
