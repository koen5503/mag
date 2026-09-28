# Trains.com Downloader - Project Regels & Architectuur

## ⚠️ 1. DE VIEWER INTERFACE IS ESSENTIEEL EN VERPLICHT
- **Reden**: De bestandsnamen en URL-structuren van PDF's op Trains.com zijn over de jaren, decennia en bladen heen volstrekt inconsistent (bijv. `MAG-TRN-DEC20-1.pdf`, `TRN_0170_cov.pdf`, `MAG-TRN-NOV20.pdf`, etc.).
- **Regel**: Probeer NOOIT directe PDF-URL's te raden of af te leiden via willekeurige patronen.
- **Verplichte flow**:
  1. Navigeer naar de issue pagina (`https://www.trains.com/{brand}/magazine/{slug}/`).
  2. Klik op de **"PDF Edition"** knop (`button.ci-btn--primary`).
  3. Wacht tot de **Viewer toolbar** geladen is.
  4. Klik op de **Download PDF** knop in de viewer (`[title='Download PDF']` of `.flipbook-btn-download`).
  5. Vang het Playwright download event op en sla het bestand op.

## 2. AANTAL NUMMERS PER JAAR IS DYNAMISCH (NIET VAST JAN-DEC)
- Sommige bladen zijn kwartaalbladen (bijv. *Classic Trains* heeft 4 nummers: Fall, Summer, Spring, Winter).
- Sommige bladen hebben 6, 9 of 12 nummers, of speciale jubileumnummers/jaarboeken.
- **Regel**: Ga NOOIT uit van een vaste Jan-Dec reeks. Inspecteer altijd dynamisch de archive pagina (`?archive_year={year}`) en haal de daadwerkelijk aanwezige issues op via `.tagged-grid-card`.
- Houd per jaar een dynamische nummering aan (#1, #2, #3, ...) gebaseerd op wat er daadwerkelijk bestaat.

## 3. DOWNLOADLOCATIE IS INSTELBAAR
- De downloadlocatie is door de gebruiker instelbaar in de Web UI en wordt opgeslagen in `config.json`.
- Het script moet altijd de geconfigureerde downloadmap respecteren.

## 4. PLAYWRIGHT THREAD-SAFETY
- Playwright sync objecten mogen NOOIT gedeeld worden over verschillende Python threads.
- Maak de Playwright browser-instantie altijd aan binnen de worker thread en sluit hem netjes af in een `finally` blok.
