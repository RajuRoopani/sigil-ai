import asyncio
from playwright.async_api import async_playwright

SCREENSHOTS_DIR = "/Users/rajuroopani/Work6/experiments/anyrepo-smes/screenshots"
BASE_URL = "http://localhost:8003"


async def scroll_to_and_screenshot(page, selector_or_js, filename, wait_ms=800):
    """Scroll an element into view using JS and take a screenshot."""
    try:
        await page.evaluate(f"""
            (() => {{
                const el = document.querySelector('{selector_or_js}');
                if (el) el.scrollIntoView({{ behavior: 'instant', block: 'start' }});
            }})()
        """)
    except Exception:
        pass
    await page.wait_for_timeout(wait_ms)
    await page.screenshot(path=f"{SCREENSHOTS_DIR}/{filename}", full_page=False)
    print(f"   Saved {filename}")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=2,
        )
        page = await context.new_page()

        # 1. hero.png
        print("1. hero.png")
        await page.goto(BASE_URL, wait_until="networkidle", timeout=15000)
        await page.wait_for_timeout(1000)
        await page.screenshot(path=f"{SCREENSHOTS_DIR}/hero.png", full_page=False)
        print("   Saved hero.png")

        # 2. hero-filled.png
        print("2. hero-filled.png")
        await page.fill('#repo-input', "vercel/next.js")
        await page.fill('#username-input', "timneutkens")
        await page.wait_for_timeout(500)
        await page.screenshot(path=f"{SCREENSHOTS_DIR}/hero-filled.png", full_page=False)
        print("   Saved hero-filled.png")

        # 3. profile-hero.png — Click extract, wait, reload with JS
        print("3. profile-hero.png")
        await page.click('#analyze-btn')
        await page.wait_for_timeout(5000)

        # Reload and inject cached profile
        await page.goto(BASE_URL, wait_until="networkidle", timeout=15000)
        await page.wait_for_timeout(1000)
        await page.evaluate("""
            () => {
                return fetch('/api/analyze', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({repo: 'vercel/next.js', username: 'timneutkens'})
                }).then(r => r.json()).then(d => {
                    currentProfile = d.profile;
                    cacheKey = d.cache_key;
                    renderResults(d.profile);
                    return 'ok';
                });
            }
        """)
        await page.wait_for_timeout(3000)
        # Scroll to profile hero
        await scroll_to_and_screenshot(page, '#profile-hero', 'profile-hero.png', 1000)

        # 4. mindmap.png
        print("4. mindmap.png")
        await scroll_to_and_screenshot(page, '#mindmap-section', 'mindmap.png', 1500)

        # 5. skills-grid.png
        print("5. skills-grid.png")
        await scroll_to_and_screenshot(page, '#skills-grid', 'skills-grid.png')

        # 6. feature-areas.png
        print("6. feature-areas.png")
        await scroll_to_and_screenshot(page, '#feature-areas-wrap', 'feature-areas.png')

        # 7. patterns.png
        print("7. patterns.png")
        await scroll_to_and_screenshot(page, '#patterns-grid', 'patterns.png')

        # 8. commits.png — expand the commits section
        print("8. commits.png")
        await page.evaluate("""
            (() => {
                const el = document.querySelector('#commits-section');
                if (el) el.scrollIntoView({ behavior: 'instant', block: 'start' });
            })()
        """)
        await page.wait_for_timeout(500)
        # Click the toggle to expand
        try:
            await page.click('#commits-toggle', timeout=3000)
        except Exception:
            # Try clicking the section header
            try:
                await page.click('#commits-section', timeout=2000)
            except Exception:
                pass
        await page.wait_for_timeout(1000)
        await page.screenshot(path=f"{SCREENSHOTS_DIR}/commits.png", full_page=False)
        print("   Saved commits.png")

        # 9. agent-files.png
        print("9. agent-files.png")
        await scroll_to_and_screenshot(page, '#md-viewer', 'agent-files.png')

        # 10. past-sigils.png
        print("10. past-sigils.png")
        await scroll_to_and_screenshot(page, '#past-section', 'past-sigils.png')

        # --- Pitch deck ---
        print("\n--- Pitch Deck ---")

        # 11. pitch-slide1.png
        print("11. pitch-slide1.png")
        await page.goto(f"{BASE_URL}/pitch", wait_until="networkidle", timeout=15000)
        await page.wait_for_timeout(2000)
        await page.screenshot(path=f"{SCREENSHOTS_DIR}/pitch-slide1.png", full_page=False)
        print("   Saved pitch-slide1.png")

        # 12. pitch-slide2.png
        print("12. pitch-slide2.png")
        await page.keyboard.press("ArrowRight")
        await page.wait_for_timeout(1200)
        await page.screenshot(path=f"{SCREENSHOTS_DIR}/pitch-slide2.png", full_page=False)
        print("   Saved pitch-slide2.png")

        # 13. pitch-slide4.png (need to go from slide 2 to slide 4 = 2 more presses)
        print("13. pitch-slide4.png")
        await page.keyboard.press("ArrowRight")
        await page.wait_for_timeout(800)
        await page.keyboard.press("ArrowRight")
        await page.wait_for_timeout(1200)
        await page.screenshot(path=f"{SCREENSHOTS_DIR}/pitch-slide4.png", full_page=False)
        print("   Saved pitch-slide4.png")

        # 14. pitch-slide6.png (from slide 4 to 6 = 2 more)
        print("14. pitch-slide6.png")
        await page.keyboard.press("ArrowRight")
        await page.wait_for_timeout(800)
        await page.keyboard.press("ArrowRight")
        await page.wait_for_timeout(1200)
        await page.screenshot(path=f"{SCREENSHOTS_DIR}/pitch-slide6.png", full_page=False)
        print("   Saved pitch-slide6.png")

        # 15. pitch-slide9.png (from slide 6 to 9 = 3 more)
        print("15. pitch-slide9.png")
        await page.keyboard.press("ArrowRight")
        await page.wait_for_timeout(800)
        await page.keyboard.press("ArrowRight")
        await page.wait_for_timeout(800)
        await page.keyboard.press("ArrowRight")
        await page.wait_for_timeout(1200)
        await page.screenshot(path=f"{SCREENSHOTS_DIR}/pitch-slide9.png", full_page=False)
        print("   Saved pitch-slide9.png")

        await browser.close()
        print(f"\nAll 15 screenshots saved to {SCREENSHOTS_DIR}/")


if __name__ == "__main__":
    asyncio.run(main())
