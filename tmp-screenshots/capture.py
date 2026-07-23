from pathlib import Path

from playwright.sync_api import sync_playwright

out = Path(r"C:\Project\teledrive\tmp-screenshots")
out.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto("http://127.0.0.1:5173", wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(800)
    page.screenshot(path=str(out / "01-login.png"), full_page=True)

    email = page.locator('input[name="email"], input[type="email"]')
    password = page.locator('input[name="password"], input[type="password"]')
    if email.count() and password.count():
        email.fill("support@99apps.id")
        password.fill("TeleDrive-Dev-2026!")
        page.get_by_role("button", name="Sign in").click()
        page.wait_for_timeout(2500)
        page.screenshot(path=str(out / "02-app.png"), full_page=True)

        api = page.get_by_test_id("nav-api-status")
        if api.count():
            api.click()
            page.wait_for_timeout(1200)
            page.screenshot(path=str(out / "03-api-webdav.png"), full_page=True)

    print("screenshots:", list(out.glob("*.png")))
    browser.close()
