from pathlib import Path
from playwright.sync_api import sync_playwright

out = Path(r"C:\Project\teledrive\tmp-screenshots")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto("http://127.0.0.1:5173", wait_until="networkidle")
    page.locator('input[type="email"]').fill("demo@99apps.id")
    page.locator('input[type="password"]').fill("TeleDrive-Demo-2026!")
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_timeout(2000)
    page.get_by_test_id("nav-api-status").click()
    page.wait_for_timeout(1500)
    page.screenshot(path=str(out / "03-api-webdav.png"), full_page=True)
    browser.close()
    print("ok")
