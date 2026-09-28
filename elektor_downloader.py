"""
Elektor Magazine Downloader - Login & Sessiebeheer
"""

import time
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, Page

SESSION_FILE = Path(__file__).parent / "session_elektor.json"


def nuke_popups_elektor(page: Page):
    """Accepteer of verwijder cookie banners en popups op Elektor."""
    try:
        # Klik op 'Akkoord' cookie button als die zichtbaar is
        btn = page.query_selector(".cc-btn.cc-dismiss, a:has-text('Akkoord')")
        if btn and btn.is_visible():
            btn.click()
            time.sleep(0.5)
    except Exception:
        pass

    try:
        page.evaluate("""() => {
            const banner = document.querySelector('.cc-window, [aria-label*=\"cookie\"][role=\"dialog\"]');
            if (banner) { banner.remove(); }
        }""")
    except Exception:
        pass


def create_elektor_browser(headless: bool = True):
    """Start Playwright browser met opgeslagen Elektor sessie indien beschikbaar."""
    p = sync_playwright().start()
    browser = p.chromium.launch(
        headless=headless,
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
    )

    storage = None
    if SESSION_FILE.exists():
        try:
            storage = json.loads(SESSION_FILE.read_text())
            print(f"   [Elektor Sessie] Cookies geladen uit {SESSION_FILE.name}")
        except Exception:
            pass

    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1400, "height": 900},
        accept_downloads=True,
        storage_state=storage,
    )
    page = context.new_page()
    page.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )
    page.set_default_navigation_timeout(60000)
    page.set_default_timeout(10000)
    return p, browser, context, page


def is_logged_in_elektor(page: Page) -> bool:
    """Controleer of we ingelogd zijn op Elektor."""
    selectors = [
        "a[href*='/account/logout']",
        "a:has-text('Uitloggen')",
        "a:has-text('Mijn account')",
        "a[href*='/account/dashboard']",
        "a[href*='/account/profile']",
    ]
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                return True
        except Exception:
            pass

    # Controleer of login knoppen ontbreken
    login_btn = page.query_selector("a[href='/account/login'], a:has-text('Inloggen')")
    # Als er GEEN login knop is maar wel account links
    if not login_btn and page.query_selector(".Header__user-menu, [class*='user-menu']"):
        return True

    return False


def login_elektor(page: Page, email: str, password: str, screenshot_path: Path = None) -> tuple[bool, str]:
    """
    Log in op Elektormagazine.nl.
    Slaat sessiecookies op in session_elektor.json bij succes.
    """
    if not email or not password:
        return False, "Geen e-mailadres of wachtwoord opgegeven voor Elektor."

    print(f"[Elektor Login] Starten voor {email}...")

    # 1. Ga naar homepage om bestaande cookies te checken
    page.goto("https://www.elektormagazine.nl/", wait_until="domcontentloaded", timeout=60000)
    nuke_popups_elektor(page)

    if is_logged_in_elektor(page):
        print("   [Elektor Login] ✅ Al ingelogd via opgeslagen sessie!")
        if screenshot_path:
            page.screenshot(path=str(screenshot_path))
        return True, "Al ingelogd via opgeslagen sessie."

    # 2. Ga naar de inlogpagina
    page.goto("https://www.elektormagazine.nl/account/login", wait_until="domcontentloaded", timeout=60000)
    nuke_popups_elektor(page)

    # 3. Formulier invullen
    try:
        email_inp = page.locator("input[name='email']").first
        email_inp.wait_for(state="visible", timeout=10000)
        email_inp.fill(email)

        pwd_inp = page.locator("input[name='password']").first
        pwd_inp.fill(password)

        # Vink eventueel 'Wachtwoord onthouden' aan
        rem = page.query_selector("#login-remember, input[name='remember']")
        if rem and not rem.is_checked():
            try: rem.check()
            except Exception: pass

        # Klik op Login
        login_btn = page.locator("button:has-text('Login'), input[type='submit'][value*='Login']").first
        login_btn.click()
        print("   [Elektor Login] Formulier verzonden, wachten op reactie...")

        # Wacht op navigatie of reactie
        time.sleep(4)
        nuke_popups_elektor(page)

    except Exception as e:
        msg = f"Fout bij invullen van Elektor login formulier: {e}"
        print(f"   ❌ {msg}")
        return False, msg

    # 4. Controleer op eventuele foutmeldingen op de pagina
    err_el = page.query_selector(".alert-danger, .error, [class*='error-message'], .c-alert--danger")
    if err_el and err_el.is_visible():
        err_msg = err_el.inner_text().strip()
        print(f"   ❌ Login afgewezen: {err_msg}")
        if screenshot_path:
            page.screenshot(path=str(screenshot_path))
        return False, f"Login afgewezen: {err_msg}"

    # 5. Verifieer of we ingelogd zijn
    if is_logged_in_elektor(page) or "account" in page.url:
        print("   [Elektor Login] ✅ Succesvol ingelogd!")
        try:
            page.context.storage_state(path=str(SESSION_FILE))
            print(f"   [Elektor Login] Sessie opgeslagen in {SESSION_FILE.name}")
        except Exception as e:
            print(f"   ⚠️  Sessie opslaan mislukt: {e}")

        if screenshot_path:
            page.screenshot(path=str(screenshot_path))

        return True, "Succesvol ingelogd op Elektor!"

    # Screenshot maken voor debug
    if screenshot_path:
        page.screenshot(path=str(screenshot_path))

    return False, "Login kon niet worden bevestigd. Controleer het screenshot of gegevens."


def parse_elektor_issue(raw_text: str, href: str, index: int, year: int) -> dict:
    """Parseert de tekst en link van een archief-item naar gestructureerde metadata."""
    import re
    raw = raw_text.strip()
    prefix = "elektor"
    if raw.startswith("i "):
        prefix = "elektor-industry"
        display_prefix = "Elektor Industry"
        num_str = raw[2:].strip()
    elif raw.startswith("e "):
        display_prefix = "Elektor"
        num_str = raw[2:].strip()
    else:
        display_prefix = "Elektor"
        num_str = raw

    m = re.search(r'(\d{4})[-_](\d+)', num_str)
    if m:
        y, n = m.group(1), int(m.group(2))
        title = f"{display_prefix} {y}-{n:02d}"
        slug = f"{prefix}-{y}-{n:02d}"
    else:
        m2 = re.search(r'(\d+)', num_str)
        if m2:
            n = int(m2.group(1))
            title = f"{display_prefix} {year}-{n:02d}"
            slug = f"{prefix}-{year}-{n:02d}"
        else:
            clean_sub = re.sub(r'[^a-zA-Z0-9]', '-', num_str).strip('-').lower()
            title = f"{display_prefix} {num_str or f'Nummer {index}'}"
            slug = f"{prefix}-{year}-{clean_sub or f'{index:02d}'}"

    return {
        "number": index,
        "title": title,
        "slug": slug,
        "href": href,
    }


def get_elektor_issues_for_year(page: Page, year: int) -> list[dict]:
    """
    Haal alle magazine issues op voor een specifiek jaar uit het Elektor archief.
    URL: https://www.elektormagazine.nl/magazine-archive/{year}
    """
    url = f"https://www.elektormagazine.nl/magazine-archive/{year}"
    print(f"[Elektor Archief] Scannen van {url}...")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        nuke_popups_elektor(page)
        page.wait_for_timeout(1000)

        # Haal alle cards op
        items_data = page.evaluate("""(curYear) => {
            const list = [];
            const cards = document.querySelectorAll('.Magazine__item');
            for (const el of cards) {
                const a = el.querySelector('a[href*="/magazine/"]');
                if (!a) continue;
                const m = el.querySelector('.Magazine__month');
                const txt = m ? m.innerText.replace(/\\s+/g, ' ').trim() : a.innerText.trim();
                if (txt || a.href) {
                    list.push({ href: a.href, text: txt });
                }
            }
            return list;
        }""", year)

        issues = []
        for idx, item in enumerate(items_data, start=1):
            if not item.get("href"):
                continue
            parsed = parse_elektor_issue(item.get("text", ""), item["href"], idx, year)
            issues.append(parsed)

        print(f"   [Elektor Archief] {len(issues)} nummers gevonden voor {year}")
        return issues
    except Exception as e:
        print(f"   ❌ Fout bij scannen van Elektor archief {year}: {e}")
        return []


def download_elektor_issue(page: Page, issue_url: str, output_dir: Path, slug: str = None, progress_cb=None) -> Path | None:
    """
    Download een individuele editie van Elektor als PDF.
    """
    def report(msg):
        print(f"   [Elektor DL] {msg}")
        if progress_cb:
            progress_cb(msg)

    output_dir.mkdir(parents=True, exist_ok=True)
    target_file = (output_dir / f"{slug}.pdf") if slug else None

    # Snelle check: reeds aanwezig?
    if target_file and target_file.exists() and target_file.stat().st_size > 1024 * 1024:
        size_mb = target_file.stat().st_size / 1024 / 1024
        report(f"⏭️ Reeds lokaal aanwezig: {target_file.name} ({size_mb:.1f} MB)")
        return target_file

    report(f"Navigeren naar {issue_url}...")
    try:
        page.goto(issue_url, wait_until="domcontentloaded", timeout=60000)
        nuke_popups_elektor(page)
    except Exception as e:
        report(f"❌ Navigatiefout: {e}")
        return None

    # Zoek download knop
    try:
        dl_btn = page.locator('a:has-text("Download magazine"), a[href*="/expose/magazine/"]').first
        dl_btn.wait_for(state="visible", timeout=15000)
    except Exception:
        report("❌ Downloadknop niet gevonden op de pagina (abonneerechten vereist).")
        return None

    report("Download starten via Elektor signed link...")
    try:
        with page.expect_download(timeout=60000) as dl_info:
            dl_btn.click()
        download = dl_info.value

        dest = target_file if target_file else (output_dir / download.suggested_filename)
        report(f"Bestand opslaan naar {dest.name}...")
        download.save_as(str(dest))

        if dest.exists() and dest.stat().st_size > 1000:
            size_mb = dest.stat().st_size / 1024 / 1024
            report(f"✅ Download voltooid: {dest.name} ({size_mb:.1f} MB)")
            return dest
        else:
            report(f"❌ Bestand te klein of leeg ({dest})")
            return None

    except Exception as e:
        report(f"❌ Downloadfout: {e}")
        return None

