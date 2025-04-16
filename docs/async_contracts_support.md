# Async Callbacks Support for Scrapy Contracts

## Overview

This implementation adds support for async callbacks in Scrapy contracts. Previously, when using async callbacks with Scrapy contracts, an error would be raised: `TypeError: Contracts don't support async callbacks`. This made it difficult to test spiders that use async callbacks, particularly those using scrapy-playwright where most calls to the browser benefit from being async.

## Changes Made

The implementation modifies the following files:

1. `scrapy/contracts/__init__.py`:
   - Updated the `add_pre_hook` method to handle async callbacks
   - Updated the `add_post_hook` method to handle async callbacks
   - Updated the `_clean_req` method to handle async callbacks

The changes use Twisted's `defer.inlineCallbacks` and `defer.ensureDeferred` to properly handle both coroutines and async generators.

## Testing the Implementation

A new test method `test_async_callbacks` has been added to the `TestContractsManager` class in `tests/test_contracts.py`. This test verifies that:

1. Contracts work with async callbacks that return items
2. Contracts work with async generators that yield items

To run the tests:

```bash
python -m pytest tests/test_contracts.py::TestContractsManager::test_async_callbacks -v
```

## Example Usage

Here's an example of how to use async callbacks with contracts in a spider:

```python
class MySpider(Spider):
    name = "my_spider"

    async def parse(self, response):
        """
        This is an async callback that returns items
        @url http://example.com
        @returns items 1 1
        """
        # Perform async operations
        await asyncio.sleep(1)
        return {"url": response.url}

    async def parse_with_generator(self, response):
        """
        This is an async generator callback that yields items
        @url http://example.com
        @returns items 1 1
        """
        # Perform async operations
        await asyncio.sleep(1)
        yield {"url": response.url}
```

## Testing with scrapy-playwright

When using scrapy-playwright, you can now test your async callbacks using contracts:

```python
class PlaywrightSpider(Spider):
    name = "playwright_spider"

    async def parse(self, response):
        """
        This is an async callback that uses playwright
        @url http://example.com
        @returns items 1 1
        """
        # Get the page from the response
        page = response.meta["playwright_page"]
        
        # Perform async operations with playwright
        await page.click("a.some-link")
        await page.wait_for_selector(".some-element")
        
        # Extract data
        title = await page.title()
        
        return {"title": title, "url": response.url}
```

## Best Practices for Testing scrapy-playwright Spiders

1. **Use Contracts for Simple Tests**: Use contracts for basic functionality tests like ensuring callbacks return the expected number of items.

2. **Mock Playwright for Unit Tests**: For more complex tests, consider mocking the Playwright page object to avoid actual browser interactions during testing.

3. **Integration Tests**: For full integration tests, set up a local test server with known content to test against.

4. **Test Each Component Separately**: Test your selectors, parsing logic, and browser interactions separately when possible.

5. **Use Explicit Waits**: Always use explicit waits (like `wait_for_selector`) rather than arbitrary sleep times to make tests more reliable.
