import asyncio
from playwright.async_api import async_playwright

async def test():
    print("Starting test...")
    async with async_playwright() as p:
        print("Launching browser...")
        browser = await p.chromium.launch(headless=True)
        print("Browser launched!")
        page = await browser.new_page()
        await page.goto("https://www.google.com")
        print("Page loaded!")
        await browser.close()
        print("Test complete!")

if __name__ == "__main__":
    asyncio.run(test())
