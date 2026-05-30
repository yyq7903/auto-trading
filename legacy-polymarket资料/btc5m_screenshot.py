import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1400, "height": 900})
        await page.goto("http://localhost:8877/", wait_until="networkidle", timeout=10000)
        await page.wait_for_timeout(2000)
        await page.screenshot(path=r"C:\Users\yyq\Desktop\btc5m_new.png", full_page=False)
        print("Done")
        await browser.close()

asyncio.run(main())
