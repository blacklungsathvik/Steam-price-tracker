# SteamTracker 🎮

> **Self-hosted Steam price intelligence, multi-region currency analytics, and empirical sale probability forecasting.**

SteamTracker tracks Steam game prices across multiple regions, detects historical all-time lows, records price movements, and predicts upcoming sale probabilities using Steam's seasonal sale cadence and official promotional calendar.

---

## Features

- **Continuous Infinite Feed:** Real-time game browsing with instant search and infinite scroll pagination.
- **Multi-Region Price Intelligence:** Compare prices across 14 global Steam currencies and storefront regions.
- **Sale Probability Forecasting:** Predicts discount likelihood and estimated drop depth for upcoming major seasonal sales.
- **All-Time Low Detection:** Identifies historical low pricing and flags active deals.
- **Official Steam Storefront API:** Uses official Steam public endpoints with respectful rate limiting (zero scraping / no IP blocks).
- **Modern Responsive UI:** Built with React 19, Vite, and dark-mode CSS variables with a built-in fallback static UI.
- **Automated Background Collector:** Continuously checks prices, updates active player counts, and discovers new titles.

---

## Tech Stack

- **Backend:** Python 3.12, Flask, SQLite3, Requests, Gunicorn
- **Frontend:** React 19, Vite, SVG Charts
- **Infrastructure:** Docker, Docker Compose, Windows Batch & Bash launchers

---

## Quick Start

### Option 1: One-Click Launcher (Windows)

Double-click `start.bat` or run:

```bat
start.bat
```

This automatically sets up a virtual environment (`.venv`), installs dependencies, and launches the server at `http://localhost:8000`.

### Option 2: Linux / macOS

```bash
chmod +x start.sh
./start.sh
```

### Option 3: Manual Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-username/steamtracker.git
   cd steamtracker
   ```

2. **Create virtual environment & install requirements:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure environment:**
   ```bash
   cp .env.example .env
   ```

4. **Build the frontend (optional if using prebuilt/fallback):**
   ```bash
   cd frontend
   npm install
   npm run build
   cd ..
   ```

5. **Start SteamTracker:**
   ```bash
   python run.py
   ```

Open [http://localhost:8000](http://localhost:8000) in your browser.

---

## Docker Deployment

Run with Docker Compose:

```bash
docker compose up -d
```

---

## Configuration (`.env`)

| Variable | Default | Description |
|---|---|---|
| `DB_PATH` | `data/tracker.db` | Path to SQLite database file |
| `TRACK_REGIONS` | `us,gb,eu,in,au,ca,br,ru,de,fr,jp,kr,sg,tr` | Comma-separated region codes |
| `STEAM_REQUEST_DELAY` | `1.6` | Delay between outbound requests (seconds) |
| `ITAD_API_KEY` | *(optional)* | IsThereAnyDeal API key for historical backfill |
| `COLLECTOR_INTERVAL_SECONDS` | `10800` | Time between collector cycles (3 hours) |
| `DETAILS_PER_CYCLE` | `60` | Number of game details refreshed per cycle |
| `ADMIN_TOKEN` | *(optional)* | Token for protecting administrative endpoints |

---

## Project Structure

```text
steamtracker/
├── app/
│   ├── analytics.py       # Price analytics, averages, time-on-sale
│   ├── collector.py       # Periodic background collector & discovery
│   ├── config.py          # Configuration parser & region divisors
│   ├── db.py              # SQLite connection & schema definitions
│   ├── external.py        # CheapShark / ITAD integrations
│   ├── predict.py         # Empirical discount & sale prediction model
│   ├── service.py         # Game & price upsert transaction services
│   ├── steam.py           # Polite Steam storefront API client
│   ├── steam_calendar.py  # Seasonal event calendar parser
│   ├── web.py             # Flask REST API & static server
│   └── static/            # Static assets & fallback UI
├── data/
│   └── steam_events.json  # Steam sale event schedule
├── frontend/              # React 19 + Vite frontend application
│   ├── src/               # React components (App, Home, Game, Chart, etc.)
│   └── package.json       # Frontend dependencies & build scripts
├── scripts/
│   └── seed_demo.py       # Seed script for initial game catalog
├── tests/                 # Unit & integration tests
├── .env.example           # Example environment template
├── .gitignore             # Comprehensive Git ignore rules
├── Dockerfile             # Container definition
├── docker-compose.yml     # Multi-service compose configuration
├── requirements.txt       # Python production dependencies
├── run.py                 # Development / single-process entry point
├── start.bat              # Windows setup and launch script
└── start.sh               # Unix setup and launch script
```

---

## License

MIT License. Not affiliated with Valve Corporation or Steam.
