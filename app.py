"""
Trains.com Magazine PDF Downloader - Flask Web UI
Start: python app.py
Open: http://localhost:5050
"""
import threading
import json
import time
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file

from downloader import (
    login, get_issues_for_year, download_issue,
    create_browser, is_logged_in, BRANDS, MONTHS_EN, SESSION_FILE
)

import os

ENV_FILE = Path(__file__).parent / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))

def get_credentials(prefix="TRAINS"):
    """Haal inloggegevens op uit environment of .env."""
    return os.getenv(f"{prefix}_EMAIL", ""), os.getenv(f"{prefix}_PASSWORD", "")


def set_credentials(email: str, pwd: str = "", prefix="TRAINS"):
    """Sla inloggegevens veilig op in lokaal .env bestand."""
    if email:
        os.environ[f"{prefix}_EMAIL"] = email
    if pwd:
        os.environ[f"{prefix}_PASSWORD"] = pwd

    env_data = {}
    if ENV_FILE.exists():
        for l in ENV_FILE.read_text().splitlines():
            if "=" in l and not l.startswith("#"):
                k, v = l.split("=", 1)
                env_data[k.strip()] = v.strip().strip("'\"")

    if email:
        env_data[f"{prefix}_EMAIL"] = email
    if pwd:
        env_data[f"{prefix}_PASSWORD"] = pwd

    lines = [f"{k}={v}" for k, v in env_data.items()]
    ENV_FILE.write_text("\n".join(lines) + "\n")


DEFAULT_DL_DIR = Path(__file__).parent / "downloads"
CONFIG_FILE    = Path(__file__).parent / "config.json"


def clean_path(path_str: str) -> str:
    """Verwijder eventuele quotes of backslashes van gekopieerde paden."""
    if not path_str:
        return ""
    s = path_str.strip().strip("'\"").strip()
    s = s.replace("\\ ", " ")
    return s


def get_config() -> dict:
    default = {
        "download_dir": str(Path("/Users/koen/Library/CloudStorage/OneDrive-Personal 2/Archief/Magazines/Trains")),
        "elektor_download_dir": str(Path("/Users/koen/Library/CloudStorage/OneDrive-Personal 2/Archief/Magazines/Elektor")),
    }
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text())
            default.update(cfg)
        except Exception:
            pass
    return default


def set_config_value(key: str, val: str) -> str:
    cfg = get_config()
    clean = clean_path(val)
    p = Path(clean).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    cfg[key] = str(p)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    return str(p)


def get_download_dir(site="trains") -> Path:
    cfg = get_config()
    key = "elektor_download_dir" if site == "elektor" else "download_dir"
    p = Path(cfg.get(key, DEFAULT_DL_DIR)).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def set_download_dir(path_str: str) -> Path:
    s = set_config_value("download_dir", path_str)
    return Path(s)




app = Flask(__name__)

_status = {"running": False, "log": [], "done": [], "errors": []}


def log(msg):
    print(msg)
    _status["log"].append(msg)
    if len(_status["log"]) > 300:
        _status["log"] = _status["log"][-300:]


def run_downloads(brand, year_from, year_to, selected_slugs=None, selected_numbers=None, custom_dir=None):
    global _status
    _status["running"] = True
    _status["log"] = []
    _status["done"] = []
    _status["errors"] = []

    # Bepaal downloadmap
    if custom_dir:
        base_dir = set_download_dir(custom_dir)
    else:
        base_dir = get_download_dir()
    log(f"📁 Downloadlocatie: {base_dir}")

    p = browser = context = page = None
    try:
        log("[Browser] Browser initialiseren in download thread...")
        p, browser, context, page = create_browser(headless=True)

        log("[Login] Sessie controleren...")
        email, pwd = get_credentials()
        ok = login(page, email, pwd)
        if not ok:
            log("❌ Login kon niet worden bevestigd!")
            return

        for year in range(year_from, year_to + 1):
            log(f"\n📅 Jaar {year} — {brand.upper()}")
            issues = get_issues_for_year(page, brand, year)

            if not issues:
                log(f"   ⚠️  Geen nummers gevonden voor {brand.upper()} {year}")
                continue

            # Filteren indien specifieke nummers of slugs zijn gekozen
            to_download = issues
            if selected_slugs:
                to_download = [i for i in issues if i['slug'] in selected_slugs]
            elif selected_numbers:
                nums_set = {str(n) for n in selected_numbers}
                to_download = [i for i in issues if str(i['number']) in nums_set]

            log(f"   {len(to_download)} van de {len(issues)} nummers te downloaden voor {year}")

            for idx, issue in enumerate(to_download):
                output_dir = base_dir / brand / str(year)
                slug = issue['slug']
                target_file = output_dir / f"{slug}.pdf"

                # Direct overslaan als het bestand al lokaal aanwezig is
                if target_file.exists() and target_file.stat().st_size > 1024 * 1024:
                    size_mb = target_file.stat().st_size / 1024 / 1024
                    log(f"   ⏭️  [#{issue['number']}] Al aanwezig: {target_file.name} ({size_mb:.1f} MB)")
                    _status["done"].append(str(target_file))
                    continue

                log(f"⬇️  [#{issue['number']} van {len(issues)}] {issue['title']}...")
                result = download_issue(
                    page, issue['href'], output_dir,
                    progress_cb=lambda msg: log(f"      {msg}")
                )
                if result:
                    _status["done"].append(str(result))
                    size_mb = result.stat().st_size / 1024 / 1024
                    log(f"   ✅ Voltooid: {result.name} ({size_mb:.1f} MB)")
                else:
                    _status["errors"].append(issue['href'])
                    log(f"   ❌ Kon niet downloaden: {issue['title']}")

        log(f"\n🎉 Klaar! Totaal: {len(_status['done'])} verwerkt, {len(_status['errors'])} fouten.")

    except Exception as e:
        log(f"❌ Onverwachte fout: {e}")
        import traceback
        log(traceback.format_exc())
    finally:
        if browser:
            try: browser.close()
            except Exception: pass
        if p:
            try: p.stop()
            except Exception: pass
        _status["running"] = False


def run_elektor_downloads(year_from, year_to, selected_slugs=None, selected_numbers=None, custom_dir=None):
    global _status
    _status["running"] = True
    _status["log"] = []
    _status["done"] = []
    _status["errors"] = []

    if custom_dir:
        base_dir = set_config_value("elektor_download_dir", custom_dir)
        base_dir = Path(base_dir)
    else:
        base_dir = get_download_dir("elektor")
    log(f"📁 Downloadlocatie (Elektor): {base_dir}")

    from elektor_downloader import (
        create_elektor_browser, login_elektor,
        get_elektor_issues_for_year, download_elektor_issue
    )

    p = browser = context = page = None
    try:
        log("[Browser] Elektor browser starten...")
        p, browser, context, page = create_elektor_browser(headless=True)

        email, pwd = get_credentials(prefix="ELEKTOR")
        ok, msg = login_elektor(page, email, pwd)
        if not ok:
            log(f"❌ Elektor inloggen mislukt: {msg}")
            return

        for year in range(year_from, year_to + 1):
            log(f"\n📅 Jaar {year} — ELEKTOR")
            issues = get_elektor_issues_for_year(page, year)
            if not issues:
                log(f"   ⚠️  Geen nummers gevonden voor Elektor {year}")
                continue

            to_download = issues
            if selected_slugs:
                to_download = [i for i in issues if i['slug'] in selected_slugs]
            elif selected_numbers:
                nums_set = {str(n) for n in selected_numbers}
                to_download = [i for i in issues if str(i['number']) in nums_set]

            log(f"   {len(to_download)} van de {len(issues)} nummers te downloaden voor {year}")

            for idx, issue in enumerate(to_download):
                output_dir = base_dir / str(year)
                slug = issue['slug']
                target_file = output_dir / f"{slug}.pdf"

                if target_file.exists() and target_file.stat().st_size > 1024 * 1024:
                    size_mb = target_file.stat().st_size / 1024 / 1024
                    log(f"   ⏭️  [#{issue['number']}] Al aanwezig: {target_file.name} ({size_mb:.1f} MB)")
                    _status["done"].append(str(target_file))
                    continue

                log(f"⬇️  [#{issue['number']} van {len(issues)}] {issue['title']}...")
                result = download_elektor_issue(
                    page, issue['href'], output_dir, slug=slug,
                    progress_cb=lambda msg: log(f"      {msg}")
                )
                if result:
                    _status["done"].append(str(result))
                    size_mb = result.stat().st_size / 1024 / 1024
                    log(f"   ✅ Voltooid: {result.name} ({size_mb:.1f} MB)")
                else:
                    _status["errors"].append(issue['href'])
                    log(f"   ❌ Kon niet downloaden: {issue['title']}")

        log(f"\n🎉 Klaar! Totaal: {len(_status['done'])} verwerkt, {len(_status['errors'])} fouten.")

    except Exception as e:
        log(f"❌ Onverwachte fout: {e}")
        import traceback
        log(traceback.format_exc())
    finally:
        if browser:
            try: browser.close()
            except Exception: pass
        if p:
            try: p.stop()
            except Exception: pass
        _status["running"] = False


@app.route("/")
def index():
    return render_template("index.html", brands=BRANDS)


@app.route("/api/status")
def status():
    return jsonify(_status)


@app.route("/api/issues")
def get_issues_api():
    site = request.args.get("site", "trains")
    try:
        year = int(request.args.get("year", 2020))
    except ValueError:
        year = 2020

    if site == "elektor":
        from elektor_downloader import create_elektor_browser, get_elektor_issues_for_year
        p = browser = context = page = None
        try:
            p, browser, context, page = create_elektor_browser(headless=True)
            issues = get_elektor_issues_for_year(page, year)
            return jsonify({"ok": True, "site": "elektor", "year": year, "issues": issues, "count": len(issues)})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e), "issues": [], "count": 0}), 500
        finally:
            if browser:
                try: browser.close()
                except Exception: pass
            if p:
                try: p.stop()
                except Exception: pass

    # Standaard Trains.com
    brand = request.args.get("brand", "trn")
    p = browser = context = page = None
    try:
        p, browser, context, page = create_browser(headless=True)
        issues = get_issues_for_year(page, brand, year)
        return jsonify({"ok": True, "brand": brand, "year": year, "issues": issues, "count": len(issues)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "issues": [], "count": 0}), 500
    finally:
        if browser:
            try: browser.close()
            except Exception: pass
        if p:
            try: p.stop()
            except Exception: pass


@app.route("/api/config", methods=["GET", "POST"])
def config_route():
    if request.method == "POST":
        data = request.json or {}
        resp = {"ok": True}

        if "download_dir" in data and data["download_dir"]:
            resp["download_dir"] = set_config_value("download_dir", data["download_dir"])

        if "elektor_download_dir" in data and data["elektor_download_dir"]:
            resp["elektor_download_dir"] = set_config_value("elektor_download_dir", data["elektor_download_dir"])

        if "email" in data or "password" in data:
            set_credentials(data.get("email", ""), data.get("password", ""), prefix="TRAINS")
            resp["email"] = os.getenv("TRAINS_EMAIL", "")

        if "elektor_email" in data or "elektor_password" in data:
            set_credentials(data.get("elektor_email", ""), data.get("elektor_password", ""), prefix="ELEKTOR")
            resp["elektor_email"] = os.getenv("ELEKTOR_EMAIL", "")

        return jsonify(resp)

    cfg = get_config()
    t_email, t_pwd = get_credentials(prefix="TRAINS")
    e_email, e_pwd = get_credentials(prefix="ELEKTOR")

    return jsonify({
        "download_dir": cfg["download_dir"],
        "elektor_download_dir": cfg["elektor_download_dir"],
        "email": t_email,
        "has_password": bool(t_pwd),
        "elektor_email": e_email,
        "has_elektor_password": bool(e_pwd)
    })


@app.route("/api/elektor/test_login", methods=["POST"])
def elektor_test_login():
    data = request.json or {}
    email = data.get("email", "").strip()
    pwd   = data.get("password", "").strip()

    if email or pwd:
        set_credentials(email, pwd, prefix="ELEKTOR")

    email, pwd = get_credentials(prefix="ELEKTOR")
    if not email or not pwd:
        return jsonify({"ok": False, "msg": "Vul eerst een e-mailadres en wachtwoord in voor Elektor."}), 400

    from elektor_downloader import create_elektor_browser, login_elektor

    p = browser = context = page = None
    try:
        p, browser, context, page = create_elektor_browser(headless=True)
        shot_path = Path(__file__).parent / "static" / "elektor_login_result.png"
        ok, msg = login_elektor(page, email, pwd, screenshot_path=shot_path)
        return jsonify({
            "ok": ok,
            "msg": msg,
            "screenshot": f"/static/elektor_login_result.png?t={int(time.time())}"
        })
    except Exception as e:
        return jsonify({"ok": False, "msg": f"Fout bij inloggen: {e}"}), 500
    finally:
        if browser:
            try: browser.close()
            except Exception: pass
        if p:
            try: p.stop()
            except Exception: pass



@app.route("/api/start", methods=["POST"])
def start():
    if _status["running"]:
        return jsonify({"ok": False, "msg": "Er draait al een download taak!"})

    data = request.json or {}
    site             = data.get("site", "trains")
    brand            = data.get("brand", "trn")
    year_from        = int(data.get("year_from", 2020))
    year_to          = int(data.get("year_to",   2020))
    selected_slugs   = data.get("slugs", [])
    selected_numbers = data.get("numbers", [])
    custom_dir       = data.get("download_dir", "").strip()

    if site == "elektor":
        t = threading.Thread(
            target=run_elektor_downloads,
            args=(year_from, year_to, selected_slugs, selected_numbers, custom_dir),
            daemon=True
        )
    else:
        t = threading.Thread(
            target=run_downloads,
            args=(brand, year_from, year_to, selected_slugs, selected_numbers, custom_dir),
            daemon=True
        )
    t.start()
    return jsonify({"ok": True, "msg": "Download gestart!"})


@app.route("/api/files")
def list_files():
    site = request.args.get("site", "trains")
    files = []
    seen_paths = set()
    current_dir = get_download_dir(site)

    search_dirs = [current_dir]
    if site == "trains" and DEFAULT_DL_DIR.exists() and DEFAULT_DL_DIR != current_dir:
        search_dirs.append(DEFAULT_DL_DIR)

    for base in search_dirs:
        if base.exists():
            for f in sorted(base.rglob("*.pdf")):
                if f.stat().st_size > 1000 and str(f) not in seen_paths:
                    seen_paths.add(str(f))
                    try:
                        rel = str(f.relative_to(base))
                    except ValueError:
                        rel = f.name
                    files.append({
                        "name": f.name,
                        "path": str(f),
                        "size_mb": round(f.stat().st_size / 1024 / 1024, 1),
                        "rel": rel,
                    })
    return jsonify(files)


@app.route("/api/download/<path:rel_path>")
def download_file(rel_path):
    site = request.args.get("site", "trains")
    current_dir = get_download_dir(site)
    path = current_dir / rel_path
    if not path.exists():
        # Kijk in alternatieve dirs
        alt_site = "elektor" if site == "trains" else "trains"
        alt_dir = get_download_dir(alt_site)
        path = alt_dir / rel_path
    if not path.exists():
        path = DEFAULT_DL_DIR / rel_path
    if not path.exists():
        return "Niet gevonden", 404
    return send_file(str(path), as_attachment=True)



if __name__ == "__main__":
    import socket
    port = 5050
    while port < 5060:
        try:
            s = socket.socket(); s.bind(("", port)); s.close(); break
        except Exception:
            port += 1
    print(f"🚂 Trains Downloader op http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
