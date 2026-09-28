"""
Trains.com Magazine PDF Downloader
Flow via de officiële viewer:
  1. Hergebruik sessie / cookies
  2. Archive pagina scannen op issues voor een jaar
  3. Per issue: open pagina -> klik 'PDF Edition' -> viewer opent
  4. In viewer: klik '[title='Download PDF']' -> browser vangt download op
  5. Opslaan in downloads/{brand}/{year}/{slug}.pdf
"""

import time
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, Page

SESSION_FILE = Path(__file__).parent / "session_cookies.json"

BRANDS = {
    "trains":             "trn",
    "model-railroader":   "mrr",
    "classic-trains":     "ctr",
    "classic-toy-trains": "ctt",
    "garden-railways":    "grw",
    "finescale-modeler":  "fsm",
}

MONTHS_EN = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december"
]


def nuke_popups(page: Page):
    """Verwijder eventuele consent dialogs en backdrops."""
    try:
        page.evaluate("""() => {
            ['.fc-consent-root','.fc-dialog-overlay','.cky-consent-container',
             '.cky-consent-bar','#onetrust-banner-sdk','.trains-overlay',
             '.trains-exclusive-badge--overlay','.modal-backdrop',
            ].forEach(sel => document.querySelectorAll(sel).forEach(el => {
                el.style.display='none'; try{el.remove();}catch(e){}
            }));
            document.querySelectorAll('.modal:not(#sign-in)').forEach(el => {
                el.style.display='none'; el.classList.remove('show','in');
                try{el.remove();}catch(e){}
            });
            document.body.style.overflow='auto';
            document.body.style.paddingRight='';
            document.body.classList.remove('modal-open');
        }""")
    except Exception:
        pass


def create_browser(headless: bool = True):
    """Start Playwright browser met opgeslagen sessie."""
    p = sync_playwright().start()
    browser = p.chromium.launch(
        headless=headless,
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
    )

    storage = None
    if SESSION_FILE.exists():
        try:
            storage = json.loads(SESSION_FILE.read_text())
            print(f"   [Sessie] Cookies geladen uit {SESSION_FILE.name}")
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


def is_logged_in(page: Page) -> bool:
    """Controleer of we ingelogd zijn."""
    for sel in ["a:has-text('My Benefits')", "a:has-text('Sign Out')", "span:has-text('Hello')"]:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                return True
        except Exception:
            pass
    return False


def login(page: Page, email: str, password: str) -> bool:
    """Login op trains.com. Slaat cookies op bij succes."""
    print("[Login] Controleren sessie...")
    page.goto("https://www.trains.com/", wait_until="domcontentloaded", timeout=60000)

    if is_logged_in(page):
        print("   [Login] ✅ Al ingelogd via opgeslagen sessie!")
        return True

    time.sleep(1.5)
    if is_logged_in(page):
        print("   [Login] ✅ Ingelogd!")
        return True

    print(f"   [Login] Niet ingelogd, starten login voor {email}...")

    # Cookie consent
    for frame in [page] + list(page.frames):
        try:
            el = frame.query_selector(".fc-cta-consent")
            if el and el.is_visible():
                el.click(timeout=3000)
                time.sleep(1)
                break
        except Exception:
            pass

    for frame in [page] + list(page.frames):
        try:
            el = frame.query_selector("[data-cky-tag='accept-button']")
            if el and el.is_visible():
                el.click(timeout=3000)
                time.sleep(1)
                break
        except Exception:
            pass

    nuke_popups(page)

    # Open login modal
    page.evaluate("""() => {
        if (window.$) { $('#sign-in').modal('show'); }
        else {
            const m = document.getElementById('sign-in');
            if (m) {
                m.style.setProperty('display','block','important');
                m.style.setProperty('opacity','1','important');
                m.classList.add('show','in');
                document.body.classList.add('modal-open');
            }
        }
    }""")
    time.sleep(1)

    # CDP input
    cdp = page.context.new_cdp_session(page)
    doc = cdp.send("DOM.getDocument")
    root_id = doc["root"]["nodeId"]

    email_node = cdp.send("DOM.querySelector", {"nodeId": root_id, "selector": "#email"})["nodeId"]
    cdp.send("DOM.focus", {"nodeId": email_node})
    for ch in email:
        cdp.send("Input.dispatchKeyEvent", {"type": "char", "text": ch})
        time.sleep(0.02)

    cdp.send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Tab", "code": "Tab"})
    cdp.send("Input.dispatchKeyEvent", {"type": "keyUp",   "key": "Tab", "code": "Tab"})
    time.sleep(0.1)

    for ch in password:
        cdp.send("Input.dispatchKeyEvent", {"type": "char", "text": ch})
        time.sleep(0.02)

    login_node = cdp.send("DOM.querySelector", {"nodeId": root_id, "selector": "#login-button"})["nodeId"]
    obj = cdp.send("DOM.resolveNode", {"nodeId": login_node})
    cdp.send("Runtime.callFunctionOn", {
        "objectId": obj["object"]["objectId"],
        "functionDeclaration": "function() { this.click(); }",
        "returnByValue": True,
    })
    print("   [Login] Inlogformulier verzonden...")
    time.sleep(6)

    nuke_popups(page)
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    nuke_popups(page)

    if is_logged_in(page):
        print("   [Login] ✅ Ingelogd!")
        try:
            page.context.storage_state(path=str(SESSION_FILE))
            print(f"   [Login] Sessie opgeslagen in {SESSION_FILE.name}")
        except Exception as e:
            print(f"   [Login] Opslaan mislukt: {e}")
        return True

    print("   [Login] ❌ Login kon niet worden bevestigd")
    return False


def get_issues_for_year(page: Page, brand: str, year: int) -> list[dict]:
    """
    Haal alle daadwerkelijke magazine issues op voor een jaar via de archive pagina.
    Werkt universeel voor alle bladen en jaartallen (kwartaalbladen, 12 nummers, specials).
    """
    url = f"https://www.trains.com/{brand}/magazine/?archive_year={year}"
    print(f"[Archive] {url}")
    page.goto(url, wait_until="domcontentloaded", timeout=60000)

    try:
        page.wait_for_selector(".tagged-grid-card, article[class*='grid-card']", timeout=8000)
    except Exception:
        pass

    nuke_popups(page)

    issues = page.evaluate(f"""() => {{
        const cards = document.querySelectorAll('.tagged-grid-card, article[class*="grid-card"], [class*="magazine-issue"]');
        const results = [];
        const seen = new Set();
        
        cards.forEach((el, index) => {{
            const a = el.querySelector('a');
            if (!a || !a.href) return;
            const href = a.href;
            if (seen.has(href)) return;
            seen.add(href);
            
            const titleEl = el.querySelector('h3, .title, [class*="title"]');
            let title = titleEl ? titleEl.innerText.trim() : (el.innerText || '').trim();
            const parts = href.split('/').filter(Boolean);
            const slug = parts[parts.length - 1];
            
            results.push({{
                number: index + 1,
                title: title || slug,
                slug: slug,
                href: href
            }});
        }});
        
        // Fallback als er geen grid-cards zijn
        if (results.length === 0) {{
            document.querySelectorAll('a[href*="/{brand}/magazine/"]').forEach((a) => {{
                const href = a.href;
                if (href.includes('archive_year') || href.endsWith('/magazine/') || 
                    href.includes('/staff') || href.includes('/guidelines') || href.includes('/annual-index') ||
                    seen.has(href)) return;
                seen.add(href);
                const parts = href.split('/').filter(Boolean);
                const slug = parts[parts.length - 1];
                results.push({{
                    number: results.length + 1,
                    title: a.innerText.trim() || slug,
                    slug: slug,
                    href: href
                }});
            }});
        }}
        
        return results;
    }}""")
    print(f"   {len(issues)} issues gevonden voor {brand} {year}")
    return issues


def download_issue_via_viewer(page: Page, issue_url: str, output_dir: Path, progress_cb=None) -> Path | None:
    """
    Download PDF van een issue via de viewer (de universele methode):
      1. Sla over als het bestand al lokaal bestaat
      2. Navigeer naar de issue pagina
      3. Controleer of nummer locked is (paywall)
      4. Klik 'PDF Edition' knop om de viewer te openen
      5. Wacht op '[title="Download PDF"]' in de toolbar
      6. Klik download knop en sla het bestand op
    """
    slug = issue_url.rstrip('/').split('/')[-1]
    filename = f"{slug}.pdf"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / filename

    if output_path.exists() and output_path.stat().st_size > 1024 * 1024:
        size_mb = output_path.stat().st_size / 1024 / 1024
        print(f"   ⏭️  Al aanwezig: {output_path.name} ({size_mb:.1f} MB)")
        return output_path

    print(f"[Download] {issue_url}")
    if progress_cb:
        progress_cb(f"Pagina laden: {slug}...")

    page.goto(issue_url, wait_until="domcontentloaded", timeout=60000)
    nuke_popups(page)

    # Paywall check
    if page.query_selector('.ci-btn--locked'):
        print("   ⚠️  PDF is vergrendeld (geen Unlimited toegang voor dit nummer)")
        if progress_cb:
            progress_cb("Vergrendeld: geen toegang tot dit nummer")
        return None

    # Zoek de PDF Edition knop
    edition_btn = page.locator("button.ci-btn--primary, .ci-btn--primary, button:has-text('PDF Edition')").first
    try:
        edition_btn.wait_for(state="visible", timeout=10000)
    except Exception:
        # Als er geen knop is, zoek naar directe download link
        direct = page.query_selector("a.ci-btn--secondary[href*='.pdf']")
        if direct:
            direct_url = direct.get_attribute("href")
            if direct_url:
                if progress_cb: progress_cb(f"Directe link downloaden: {filename}...")
                with page.expect_download(timeout=90000) as dl_info:
                    page.evaluate(f"window.location.href = '{direct_url}'")
                dl = dl_info.value
                dl.save_as(str(output_path))
                size_mb = output_path.stat().st_size / 1024 / 1024
                print(f"   ✅ Opgeslagen via directe link: {output_path.name} ({size_mb:.1f} MB)")
                return output_path
        print(f"   ❌ Geen PDF Edition knop gevonden op {issue_url}")
        return None

    # Klik PDF Edition knop om de viewer te openen
    if progress_cb:
        progress_cb(f"Viewer openen: {filename}...")
    edition_btn.scroll_into_view_if_needed()
    edition_btn.click()

    # Wacht op de download knop in de toolbar van de viewer
    dl_selectors = [
        "[title='Download PDF']",
        "[title*='Download' i]",
        "[aria-label*='Download' i]",
        ".flipbook-btn-download",
        "[title*='PDF' i]"
    ]

    dl_btn = None
    for sel in dl_selectors:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="attached", timeout=6000)
            dl_btn = loc
            break
        except Exception:
            continue

    if not dl_btn:
        # Probeer coördinaten van title="Download PDF" via JS
        pos = page.evaluate("""() => {
            const el = document.querySelector('[title="Download PDF"], [title*="Download" i]');
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return {x: r.left + r.width/2, y: r.top + r.height/2};
        }""")
        if pos:
            if progress_cb: progress_cb(f"Downloaden via viewer...")
            with page.expect_download(timeout=90000) as dl_info:
                page.mouse.click(pos['x'], pos['y'])
            dl = dl_info.value
            dl.save_as(str(output_path))
            size_mb = output_path.stat().st_size / 1024 / 1024
            print(f"   ✅ Opgeslagen via viewer coördinaten: {output_path.name} ({size_mb:.1f} MB)")
            return output_path

        print("   ❌ Download knop in viewer niet gevonden")
        return None

    if progress_cb:
        progress_cb(f"Downloaden uit viewer ({filename})...")

    try:
        with page.expect_download(timeout=90000) as dl_info:
            dl_btn.click()
        dl = dl_info.value
        dl.save_as(str(output_path))
        size_mb = output_path.stat().st_size / 1024 / 1024
        print(f"   ✅ Opgeslagen via viewer: {output_path.name} ({size_mb:.1f} MB)")
        return output_path
    except Exception as e:
        print(f"   ❌ Fout bij downloaden via viewer: {e}")
        return None


# Alias voor backwards compatibility
download_issue = download_issue_via_viewer
