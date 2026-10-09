"""
Internet Archive (Archive.org) Downloader Module
Ondersteunt inspectie en betrouwbaar downloaden van PDF-collecties via de Archive.org API en HTTP streaming.
"""

import re
import urllib.request
import urllib.parse
import json
import time
from pathlib import Path


def extract_identifier(url_or_id: str) -> str:
    """
    Haalt de unieke Archive.org identifier uit een volledige URL of directe string.
    Ondersteunt:
      - https://archive.org/download/BYTE-MAGAZINE-COMPLETE
      - https://archive.org/details/BYTE-MAGAZINE-COMPLETE/
      - https://archive.org/metadata/BYTE-MAGAZINE-COMPLETE
      - BYTE-MAGAZINE-COMPLETE
    """
    if not url_or_id:
        return ""
    s = url_or_id.strip().strip("'\"").strip()
    
    # Check for archive.org URL patronen
    m = re.search(r"archive\.org/(?:download|details|metadata)/([^/?#]+)", s, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    
    # Als er query parameters of slashes aanhangen
    clean = s.split("?")[0].split("#")[0].strip("/")
    if "/" in clean:
        clean = clean.split("/")[-1]
    return clean


def inspect_archive_item(url_or_id: str) -> dict:
    """
    Haalt metadata en lijst van alle PDF-bestanden op voor een Archive.org item.
    """
    identifier = extract_identifier(url_or_id)
    if not identifier:
        return {"ok": False, "error": "Geen geldige Archive.org identifier of URL opgegeven."}

    metadata_url = f"https://archive.org/metadata/{urllib.parse.quote(identifier)}"
    print(f"[Archive.org] Metadata ophalen van {metadata_url}...")

    try:
        req = urllib.request.Request(
            metadata_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            }
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": f"Fout bij opvragen van Archive.org metadata: {e}"}

    if not data or not isinstance(data, dict):
        return {"ok": False, "error": "Geen gegevens gevonden voor deze identifier op Archive.org."}

    meta = data.get("metadata", {})
    title = meta.get("title", identifier)
    description = meta.get("description", "")
    all_files = data.get("files", [])

    # Filter alle PDF-bestanden
    pdf_files = []
    total_bytes = 0

    for f in all_files:
        name = f.get("name", "")
        if name.lower().endswith(".pdf"):
            try:
                size_bytes = int(f.get("size", 0))
            except (ValueError, TypeError):
                size_bytes = 0

            total_bytes += size_bytes
            size_mb = round(size_bytes / (1024 * 1024), 1)

            # Veilige download URL
            encoded_name = urllib.parse.quote(name)
            dl_url = f"https://archive.org/download/{identifier}/{encoded_name}"

            pdf_files.append({
                "name": name,
                "size_bytes": size_bytes,
                "size_mb": size_mb,
                "format": f.get("format", "PDF"),
                "url": dl_url,
            })

    # Natuurlijke sortering op bestandsnaam
    def natural_sort_key(s):
        return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s.get("name", ""))]

    pdf_files.sort(key=natural_sort_key)

    total_size_mb = round(total_bytes / (1024 * 1024), 1)
    total_size_gb = round(total_size_mb / 1024, 2)

    return {
        "ok": True,
        "identifier": identifier,
        "title": title,
        "description": description[:300] if description else "",
        "files": pdf_files,
        "count": len(pdf_files),
        "total_size_mb": total_size_mb,
        "total_size_gb": total_size_gb,
    }


def download_archive_file(
    url: str,
    output_path: Path,
    expected_size: int = None,
    progress_cb=None
) -> Path | None:
    """
    Downloadt een bestand van Archive.org via HTTP streaming met .part hervatting/veiligheid.
    """
    def report(msg):
        print(f"   [Archive DL] {msg}")
        if progress_cb:
            progress_cb(msg)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    part_path = output_path.with_name(output_path.name + ".part")

    # Snelle check: reeds aanwezig en compleet?
    if output_path.exists():
        actual_size = output_path.stat().st_size
        if expected_size and actual_size == expected_size:
            size_mb = actual_size / (1024 * 1024)
            report(f"⏭️  Reeds aanwezig: {output_path.name} ({size_mb:.1f} MB)")
            return output_path
        elif not expected_size and actual_size > 1024 * 1024:
            size_mb = actual_size / (1024 * 1024)
            report(f"⏭️  Reeds aanwezig: {output_path.name} ({size_mb:.1f} MB)")
            return output_path

    report(f"Downloaden van {output_path.name}...")
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            }
        )

        with urllib.request.urlopen(req, timeout=60) as resp, open(part_path, "wb") as f_out:
            total_dl = 0
            chunk_size = 128 * 1024  # 128 KB chunks
            last_report_time = time.time()

            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f_out.write(chunk)
                total_dl += len(chunk)

                # Optionele periodieke voortgangsupdate (elke 5 sec)
                now = time.time()
                if now - last_report_time > 5:
                    last_report_time = now
                    cur_mb = total_dl / (1024 * 1024)
                    if expected_size:
                        tot_mb = expected_size / (1024 * 1024)
                        pct = (total_dl / expected_size) * 100
                        report(f"   ... {cur_mb:.1f} / {tot_mb:.1f} MB ({pct:.0f}%)")

        # Verplaats .part naar definitief bestand
        part_path.replace(output_path)

        if output_path.exists() and output_path.stat().st_size > 1000:
            size_mb = output_path.stat().st_size / (1024 * 1024)
            report(f"✅ Voltooid: {output_path.name} ({size_mb:.1f} MB)")
            return output_path
        else:
            report(f"❌ Bestand te klein of leeg ({output_path.name})")
            if output_path.exists():
                output_path.unlink()
            return None

    except Exception as e:
        report(f"❌ Fout bij downloaden van {output_path.name}: {e}")
        if part_path.exists():
            try: part_path.unlink()
            except Exception: pass
        return None
