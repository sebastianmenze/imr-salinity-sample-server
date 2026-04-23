# IMR Salinity Sample Tracker

QR-code based salinity sample management for IMR research vessels.
Handles the full lifecycle from bottle collection at sea to lab measurement and upload to the PhysChem database.

Built with FastAPI + PostgreSQL, deployed via Docker.

## Workflow

```
Ship / CTD deck                          Lab
──────────────────────────────           ──────────────────────────────────────
Register sample                    →     Scan QR label
  • Upload Seabird BTL file              Enter PSAL_LAB measurement
  • or manual entry                      Auto-upload to PhysChem
Print 50×50 mm QR label                  Add replicate measurements (new ordinal)
Attach to bottle
```

## Quick Start

```bash
cp .env.example .env          # set BASE_URL, SECRET_KEY, PHYSCHEM_API_KEY
docker compose up -d
# Open http://localhost:8000
```

See **[USER_GUIDE.md](USER_GUIDE.md)** for step-by-step instructions for ship and lab personnel, including label printer setup.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://salinity:salinity@db:5432/salinity` | PostgreSQL connection string |
| `BASE_URL` | `http://nautilus.imr.no:8000` | Public URL embedded in QR codes |
| `SECRET_KEY` | `changeme` | App secret key |
| `PHYSCHEM_API_URL` | `https://physchem-api-test.hi.no` | PhysChem API base URL |
| `PHYSCHEM_API_KEY` | — | Static bearer token (alternative to Azure AD token) |

## PhysChem Integration

Authentication uses a **short-lived Azure AD token** (1 hour) pasted by the user on the measurement page, obtained from the PhysChem token portal. No server-side credentials are required.

Upload flow per sample:

1. `GET /mission/list` — find mission by cruise ID (falls back to best time/position match if no cruise ID)
2. `GET /mission/{id}/operation/list` — find CTD cast by UTC time + position
3. `GET /operation/{id}/instrument/list` — find BOT instrument
4. Match bottle by depth via PRES readings
5. `POST /instrument/{id}/parameter` — create `PSAL_LAB` parameter (`acquirementMethod=1020101`, `ordinal` auto-incremented for replicates)
6. Reading embedded in parameter creation payload

PhysChem values are fetched on every measurement page load and backfilled into the local database so historical data is available without a live connection.

## Data Model

| Table | Purpose |
|---|---|
| `salinity_samples` | One row per bottle — metadata, position, CTD sensor PSAL values, latest lab measurement |
| `sample_measurements` | One row per lab measurement — PSAL_LAB, who measured it, PhysChem reading ID and ordinal |

Multiple measurements per sample are supported (replicates get consecutive PhysChem ordinals).

## Label Printing

Labels are **50 × 50 mm** PDF (Phomemo M110 format). Download from `/label/{id}/pdf`.
Left half: metadata text (vessel, time, position, depth in bold, bottle in bold). Right half: QR code linking to the measurement page.

See the [printer setup appendix](USER_GUIDE.md#appendix--setting-up-the-phomemo-m110-on-windows-usbcsbc) in the user guide for Windows driver and label size configuration.

## Project Structure

```
app/
  main.py              # FastAPI app, startup/lifespan
  config.py            # Settings (pydantic-settings, .env)
  database.py          # SQLAlchemy engine + create_tables()
  models/
    sample.py          # SalinitySample + SampleMeasurement models
  routers/
    register.py        # Shipboard registration (BTL file + manual)
    measure.py         # Lab measurement, PhysChem upload, CSV export
    auth.py            # Token paste / logout endpoints
  utils/
    bot_parser.py      # Seabird BTL file parser
    qr_generator.py    # QR code + 50×50 mm label PDF generator
    physchem.py        # PhysChem API client (mission/operation/BOT lookup)
    azure_auth.py      # Azure AD token cache
  templates/           # Jinja2 HTML templates
  static/              # CSS
db/
  init.sql             # PostgreSQL init script (runs on first container start)
tests/
  test_bot_parser.py
USER_GUIDE.md          # End-user guide for ship and lab personnel
```

## Development

```bash
pip install -r requirements.txt
# configure DATABASE_URL in .env to point at a local Postgres instance
uvicorn app.main:app --reload

pytest tests/ -v
```
