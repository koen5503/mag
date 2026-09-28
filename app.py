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

def get_credentials():
    """Haal inloggegevens op uit environment of .env."""
    return os.getenv("TRAINS_EMAIL", ""), os.getenv("TRAINS_PASSWORD", "")


def set_credentials(email: str, pwd: str = ""):
    """Sla inloggegevens veilig op in lokaal .env bestand."""
    if email:
        os.environ["TRAINS_EMAIL"] = email
    if pwd:
        os.environ["TRAINS_PASSWORD"] = pwd

    cur_email = os.getenv("TRAINS_EMAIL", "")
    cur_pwd = os.getenv("TRAINS_PASSWORD", "")
    ENV_FILE.write_text(f"TRAINS_EMAIL={cur_email}\nTRAINS_PASSWORD={cur_pwd}\n")


DEFAULT_DL_DIR = Path(__file__).parent / "downloads"
CONFIG_FILE    = Path(__file__).parent / "config.json"


def clean_path(path_str: str) -> str:
    """Verwijder eventuele quotes of backslashes van gekopieerde paden."""
    if not path_str:
        return ""
    s = path_str.strip().strip("'\"").strip()
    s = s.replace("\\ ", " ")
    return s


def get_download_dir() -> Path:
    """Haal de geconfigureerde downloadlocatie op."""
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text())
            custom = clean_path(cfg.get("download_dir", ""))
            if custom:
                p = Path(custom).expanduser().resolve()
                p.mkdir(parents=True, exist_ok=True)
                return p
        except Exception:
            pass
    DEFAULT_DL_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_DL_DIR


def set_download_dir(path_str: str) -> Path:
    """Sla een nieuwe downloadlocatie op (schoont quotes automatisch op)."""
    clean = clean_path(path_str)
    p = Path(clean).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps({"download_dir": str(p)}, indent=2))
    return p



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


@app.route("/")
def index():
    return render_template("index.html", brands=BRANDS)


@app.route("/api/status")
def status():
    return jsonify(_status)


@app.route("/api/issues")
def get_issues_api():
    brand = request.args.get("brand", "trn")
    try:
        year = int(request.args.get("year", 2020))
    except ValueError:
        year = 2020

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
        new_dir = data.get("download_dir", "").strip()
        new_email = data.get("email", "").strip()
        new_pwd = data.get("password", "").strip()

        resp = {"ok": True}
        if new_dir:
            try:
                p = set_download_dir(new_dir)
                resp["download_dir"] = str(p)
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 400

        if new_email or new_pwd:
            try:
                set_credentials(new_email, new_pwd)
                resp["email"] = os.getenv("TRAINS_EMAIL", "")
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 400

        return jsonify(resp)

    email, pwd = get_credentials()
    return jsonify({
        "download_dir": str(get_download_dir()),
        "email": email,
        "has_password": bool(pwd)
    })


@app.route("/api/start", methods=["POST"])
def start():
    if _status["running"]:
        return jsonify({"ok": False, "msg": "Er draait al een download taak!"})

    data = request.json or {}
    brand            = data.get("brand", "trn")
    year_from        = int(data.get("year_from", 2020))
    year_to          = int(data.get("year_to",   2020))
    selected_slugs   = data.get("slugs", [])
    selected_numbers = data.get("numbers", [])
    custom_dir       = data.get("download_dir", "").strip()

    t = threading.Thread(
        target=run_downloads,
        args=(brand, year_from, year_to, selected_slugs, selected_numbers, custom_dir),
        daemon=True
    )
    t.start()
    return jsonify({"ok": True, "msg": "Download gestart!"})


@app.route("/api/files")
def list_files():
    files = []
    seen_paths = set()
    current_dir = get_download_dir()

    search_dirs = [current_dir]
    if DEFAULT_DL_DIR.exists() and DEFAULT_DL_DIR != current_dir:
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
    current_dir = get_download_dir()
    path = current_dir / rel_path
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
