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
Print 50×30 mm QR label                  Add replicate measurements (new ordinal)
Attach to bottle                         Delete a bad reading if needed
```

Every sample gets a short 8-character ID (e.g. `e2b1c9ab`) printed as a QR code on its label. Scanning it opens the measurement page directly — no searching required. A USB barcode scanner attached to any page also intercepts scanned QR codes and opens the matching measurement page in a new tab.

## Quick Start

Requires [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/) (both included with Docker Desktop; on Linux install `docker-compose-plugin`).

```bash
git clone <repository-url>
cd imr-salinity-sample-server

cp .env.example .env          # then edit .env — set BASE_URL, SECRET_KEY, PHYSCHEM_API_URL/KEY

docker compose up -d --build  # builds the app image, starts Postgres, runs migrations on startup

# Open http://localhost:8000  (or http://<server-host>:8000 on a shared machine)
```

Database tables (and any new columns added by later updates) are created automatically on startup — no manual migration step needed.

To stop the stack: `docker compose down` (add `-v` to also wipe the Postgres volume and start with an empty database).

### Updating an existing deployment

```bash
git pull
docker compose up --build -d
```

This rebuilds the app image with the latest code and restarts the containers. The database is preserved; any new columns the models require are added automatically at startup.

See **[USER_GUIDE.md](USER_GUIDE.md)** for step-by-step instructions for ship and lab personnel, including label printer setup.

## Configuration

Set these in `.env` (copied from `.env.example`) — `docker-compose.yml` passes them through to the app container.

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://salinity:salinity@db:5432/salinity` | PostgreSQL connection string |
| `BASE_URL` | `http://nautilus.imr.no:8000` | Fallback public URL for QR codes (labels actually use the request's own host, see below) |
| `SECRET_KEY` | `changeme` | App secret key |
| `PHYSCHEM_API_URL` | `https://physchem-api-test.hi.no` | PhysChem API base URL |
| `PHYSCHEM_API_KEY` | — | Static bearer token (alternative to pasting an Azure AD token per session) |
| `LABEL_PRINTER_URL` | — | Optional direct/CUPS label printer endpoint |

QR codes and label PDFs are generated using the **host of the incoming request** (`request.base_url`), so labels always point back to whichever address was used to reach the app — `BASE_URL` is only a fallback where no request context is available.

## Sample Lifecycle

| Status | Meaning |
|---|---|
| `registered` | Label printed, bottle not yet measured |
| `in_lab` | (Legacy) previously set on QR scan — scanning no longer changes status automatically |
| `measured` | Lab salinity entered, not yet uploaded to PhysChem |
| `uploaded` | Successfully uploaded to PhysChem |

Status only advances once a measurement is actually entered or uploaded — simply opening the measurement page via QR scan no longer changes it.

## PhysChem Integration

Authentication uses a **short-lived Azure AD token** (1 hour) pasted by the user on the measurement page, obtained from the PhysChem token portal. No server-side credentials are required (a static `PHYSCHEM_API_KEY` bearer token is also supported as a fallback). The upload button is disabled until a token is active.

Upload flow per sample:

1. `GET /mission/list` — find mission by cruise ID (falls back to best time/position match if no cruise ID)
2. `GET /mission/{id}/operation/list` — find CTD cast by UTC time + position
3. `GET /operation/{id}/instrument/list` — find BOT instrument
4. Match bottle by depth via PRES readings
5. `POST /instrument/{id}/parameter` — create `PSAL_LAB` parameter (`acquirementMethod=1020101`, `ordinal` auto-incremented for replicates)
6. Reading embedded in parameter creation payload

PhysChem values are fetched on every measurement page load and backfilled into the local database so historical data is available without a live connection.

A PSAL_LAB reading can be deleted from both PhysChem (`DELETE /reading/{id}`) and the local database directly from the measurement page — the local record is always removed even if the remote delete fails, so a stuck/duplicate row never blocks entering a fresh value; a failed remote delete is only shown as a warning.

## Data Model

| Table | Purpose |
|---|---|
| `salinity_samples` | One row per bottle — metadata, position, CTD sensor PSAL values, latest lab measurement, optional sampling comment |
| `sample_measurements` | One row per lab measurement — PSAL_LAB, who measured it, lab comment, PhysChem reading/parameter ID and ordinal |

Multiple measurements per sample are supported (replicates get consecutive PhysChem ordinals). New columns added to these models are added to the live database automatically on startup — no separate migration step required.

## Pages

| Page | Route | Purpose |
|---|---|---|
| Register | `/` | Register samples from a Seabird BTL file or manual entry, print labels |
| Measure | `/measure/{id}` | QR landing page — enter/upload a PSAL_LAB measurement, view/delete readings |
| All Samples | `/samples` | Full sample list with status, filters, and CSV export (`/samples/export.csv`) |
| Measured Today | `/measured-today` | Every measurement logged since midnight UTC, same table style as All Samples |
| User Guide | `/guide` | In-app rendering of `USER_GUIDE.md` for ship and lab personnel |

## Label Printing

Labels are **50 × 30 mm** PDF (Phomemo M110 format). Download from `/label/{id}/pdf`.
Left column: metadata text (vessel, time, position, depth in bold, bottle in bold). Right column: QR code with the sample's short ID printed underneath it.

See the [printer setup appendix](USER_GUIDE.md#appendix--setting-up-the-phomemo-m110-on-windows-usbcsbc) in the user guide for Windows driver and label size configuration.

## Project Structure

```
app/
  main.py              # FastAPI app, startup/lifespan, DB table creation, guide image sync
  config.py            # Settings (pydantic-settings, .env)
  database.py          # SQLAlchemy engine, create_tables(), auto-adds missing columns
  models/
    sample.py          # SalinitySample + SampleMeasurement models, short-UUID ID generation
  routers/
    register.py        # Shipboard registration (BTL file + manual), label view/PDF
    measure.py         # Lab measurement, PhysChem upload/delete, samples list, CSV export
    auth.py             # Token paste / logout endpoints
    guide.py            # Renders USER_GUIDE.md as an in-app page
  utils/
    bot_parser.py       # Seabird BTL file parser
    qr_generator.py     # QR code + 50×30 mm label PDF generator
    physchem.py         # PhysChem API client (mission/operation/BOT lookup, upload, delete)
    azure_auth.py        # Azure AD token cache
  templates/            # Jinja2 HTML templates
  static/                # CSS, synced guide images
db/
  init.sql              # PostgreSQL init script (runs on first container start)
tests/
  test_bot_parser.py
USER_GUIDE.md            # End-user guide for ship and lab personnel
```

## Development

Run the app directly against a local Postgres instance (or point `DATABASE_URL` at the Dockerized one):

```bash
pip install -r requirements.txt
cp .env.example .env          # set DATABASE_URL to point at your Postgres instance
uvicorn app.main:app --reload

pytest tests/ -v
```

Sample IDs are 8-character hex strings (`uuid4().hex[:8]`), checked against the database for collisions on creation.
