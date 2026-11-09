import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1440, 'height': 900})
        
        errors = []
        page.on('pageerror', lambda err: errors.append(str(err)))
        page.on('console', lambda msg: errors.append(f'Console error: {msg.text}') if msg.type == 'error' else None)

        print('Navigating to http://127.0.0.1:8000 ...')
        await page.goto('http://127.0.0.1:8000', wait_until='networkidle')
        await page.wait_for_timeout(1000)

        nav_buttons = await page.locator('nav button').all_text_contents()
        print(f'Total nav items: {len(nav_buttons)}')
        for idx, text in enumerate(nav_buttons):
            clean_text = ' '.join(text.split())
            print(f'  [{idx+1}] {clean_text}')

        has_reels_tab = await page.locator('#tabBtn_reels').count()
        has_reels_view = await page.locator('#view_reels').count()
        print(f'tabBtn_reels count: {has_reels_tab} (expected 0)')
        print(f'view_reels count: {has_reels_view} (expected 0)')
        assert has_reels_tab == 0, 'tabBtn_reels still exists!'
        assert has_reels_view == 0, 'view_reels still exists!'

        tabs_to_test = ['overview', 'niche_pods', 'pipeline', 'accounts', 'ingest', 'sources', 'broadcasts', 'settings']
        for tab in tabs_to_test:
            btn_id = f'#tabBtn_{tab}'
            view_id = f'#view_{tab}'
            await page.click(btn_id)
            await page.wait_for_timeout(300)
            is_visible = await page.locator(view_id).is_visible()
            print(f'Tab {tab} switched successfully, view visible: {is_visible}')
            assert is_visible, f'View {view_id} is not visible after switching to {tab}!'

        await page.screenshot(path=r'C:\Users\harsh parmar\.gemini\antigravity\brain\774a7df9-ab5a-4865-8ba5-a42753b13222\reels_removed_broadcasts.png')
        print('Captured reels_removed_broadcasts.png')

        await page.click('#tabBtn_overview')
        await page.wait_for_timeout(500)
        await page.screenshot(path=r'C:\Users\harsh parmar\.gemini\antigravity\brain\774a7df9-ab5a-4865-8ba5-a42753b13222\reels_removed_sidebar_overview.png')
        print('Captured reels_removed_sidebar_overview.png')

        print(f'Recorded JavaScript/Page errors: {len(errors)}')
        if errors:
            for e in errors:
                print(f'  Error: {e}')
        assert len(errors) == 0, f'Found console/page errors: {errors}'
        print('All assertions passed cleanly with 0 errors!')

        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
