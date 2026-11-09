import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.on("console", lambda msg: errors.append(f"Console error: {msg.text}") if msg.type == "error" else None)

        print("Navigating to http://127.0.0.1:8000 ...")
        await page.goto("http://127.0.0.1:8000", wait_until="networkidle")
        await page.wait_for_timeout(800)

        aside = page.locator("aside")
        await aside.screenshot(path=r"C:\Users\harsh parmar\.gemini\antigravity\brain\774a7df9-ab5a-4865-8ba5-a42753b13222\minimalist_sidebar_actual.png")
        print("Captured minimalist_sidebar_actual.png")

        nav_buttons = await page.locator("nav button").all_text_contents()
        print(f"Total nav items: {len(nav_buttons)}")
        for idx, text in enumerate(nav_buttons):
            clean_text = " ".join(text.split())
            print(f"  [{idx+1}] {clean_text}")

        print("Clicking Reels tab...")
        await page.click("#tabBtn_reels")
        await page.wait_for_timeout(500)
        await aside.screenshot(path=r"C:\Users\harsh parmar\.gemini\antigravity\brain\774a7df9-ab5a-4865-8ba5-a42753b13222\minimalist_sidebar_reels_active.png")
        print("Captured minimalist_sidebar_reels_active.png")

        await page.screenshot(path=r"C:\Users\harsh parmar\.gemini\antigravity\brain\774a7df9-ab5a-4865-8ba5-a42753b13222\minimalist_dashboard_reels.png")
        print("Captured minimalist_dashboard_reels.png")

        aside_scroll_w = await page.evaluate("document.querySelector('aside').scrollWidth")
        aside_client_w = await page.evaluate("document.querySelector('aside').clientWidth")
        print(f"Aside scrollWidth: {aside_scroll_w}, clientWidth: {aside_client_w} (Diff: {aside_scroll_w - aside_client_w})")
        assert aside_scroll_w <= aside_client_w, "Horizontal scroll detected in sidebar!"

        print(f"Console/Page errors: {len(errors)}")
        if errors:
            for e in errors:
                print(" ", e)
        assert len(errors) == 0, "Errors encountered!"

        await browser.close()
        print("Playwright test completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
