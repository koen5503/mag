# Trains.com Magazine Downloader Webapp

Een Python webapplicatie met een intuïtieve webinterface om automatisch edities van tijdschriften (*Trains*, *Model Railroader*, *Classic Trains*, *Classic Toy Trains*, *Garden Railways*, *Finescale Modeler*) te downloaden als PDF-bestanden vanaf Trains.com.

---

## Belangrijkste Eigenschappen

- 🌐 **Web Interface**: Volledig te bedienen via de browser op `http://localhost:5050`.
- 📖 **Essentiële Viewer-flow**: Gebruikt altijd de officiële Trains.com reader interface om downloads te initiëren. Hierdoor wordt altijd het correcte PDF-bestand gedownload, ongeacht inconsistente bestandsnamen of URL-structuren over de decennia heen.
- 🔢 **Dynamische Nummering & Archieven**: Detecteert automatisch hoeveel nummers er daadwerkelijk per jaar bestaan (kwartaalbladen, 6, 9 of 12 nummers per jaar, of jubileumnummers) en toont ze genummerd in de interface (#1, #2, #3, ...).
- 📁 **Instelbare Downloadlocatie**: Kies zelf waar de PDF's worden opgeslagen (lokaal of in de cloud zoals OneDrive) direct vanuit de interface.
- ⚡ **Snelle Stream & Lokale Cache**: Nummers die al op de schijf aanwezig zijn worden direct in 0.001s overgeslagen.
- 🔑 **Sessie-persistentie**: Logt in via CDP en bewaart sessiecookies lokaal zodat niet bij elke download opnieuw hoeft te worden ingelogd.
- 📊 **Realtime Voortgang**: Live logboek, statistieken en overzicht van gedownloade PDF's.

---

## Ondersteunde Tijdschriften

- 🚂 **Trains Magazine** (`trn`)
- 🛠️ **Model Railroader** (`mrr`)
- 🕰️ **Classic Trains** (`ctr`)
- 🚂 **Classic Toy Trains** (`ctt`)
- 🌿 **Garden Railways** (`grw`)
- 🎨 **Finescale Modeler** (`fsm`)

---

## Installatie & Gebruik

### 1. Repository klonen & dependencies installeren

```bash
git clone https://github.com/koen5503/mag.git
cd mag

# Virtuele omgeving aanmaken
python3 -m venv venv
source venv/bin/activate

# Pakketten installeren
pip install -r requirements.txt

# Playwright browser installeren
playwright install chromium
```

### 2. Inloggegevens instellen

Kopieer `.env.example` naar `.env` en vul je Trains.com abonnementsgegevens in:

```bash
cp .env.example .env
```

Bewerk `.env`:
```ini
TRAINS_EMAIL=jouw_email@voorbeeld.com
TRAINS_PASSWORD=jouw_wachtwoord
```

### 3. Server starten

```bash
python app.py
```

Open je browser op:
👉 **http://localhost:5050**

---

## Structuur van het Project

- `app.py`: Flask webserver, achtergrond worker threads en REST API.
- `downloader.py`: Kernmodule met Playwright browser-automatisering en de officiële viewer-download flow.
- `templates/index.html`: Responsive webdashboard met dynamische nummering per jaar.
- `static/`: CSS styling en frontend assets.
- `GEMINI.md`: Architectuurregels en richtlijnen voor AI pair programming.
