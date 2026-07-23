from pathlib import Path

from playwright.sync_api import sync_playwright

out = Path(r"C:\Project\teledrive\tmp-screenshots")
out.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=80)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto("http://127.0.0.1:5173", wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(1000)
    page.screenshot(path=str(out / "01-login.png"), full_page=True)

    # Prefer create-account if login fails (local DB may have changed)
    create = page.get_by_role("button", name="Create account")
    if create.count():
        create.click()
        page.wait_for_timeout(400)

    email = page.locator('input[type="email"]')
    password = page.locator('input[type="password"]')
    email.fill("demo@99apps.id")
    password.fill("TeleDrive-Demo-2026!")

    submit = page.get_by_role("button", name="Create account")
    if not submit.count():
        submit = page.get_by_role("button", name="Sign in")
    submit.first.click()
    page.wait_for_timeout(2500)

    # If email already exists, switch to sign in
    if page.get_by_text("already", exact=False).count() or page.get_by_role("alert").count():
        switch = page.get_by_role("button", name="I already have an account")
        if switch.count():
            switch.click()
            page.wait_for_timeout(300)
            email.fill("demo@99apps.id")
            password.fill("TeleDrive-Demo-2026!")
            page.get_by_role("button", name="Sign in").click()
            page.wait_for_timeout(2500)

    page.screenshot(path=str(out / "02-app.png"), full_page=True)

    api = page.get_by_test_id("nav-api-status")
    if api.count():
        api.click()
        page.wait_for_timeout(1500)
        page.screenshot(path=str(out / "03-api-webdav.png"), full_page=True)

    # Keep browser open briefly so user can see it
    page.wait_for_timeout(12000)
    browser.close()
    print("done")
