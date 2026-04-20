# IMR Salinity Sample Tracker

QR-code based salinity sample management for IMR research vessels.
Built with FastAPI + PostgreSQL, deployed via Docker.

## Workflow

**On the vessel** → Register sample (manual or Seabird BOT file) → Print QR label → Attach to bottle

**In the lab** → Scan QR code → Enter measured salinity → Auto-upload to PhysChem

## Quick Start

```bash
cp .env.example .env
docker compose up -d
# Open http://localhost:8000
```

## Development

```bash
pip install -r requirements.txt
# Set DATABASE_URL in .env to a local Postgres instance
uvicorn app.main:app --reload

# Run tests
pytest tests/ -v
```

## Project Structure

```
app/
  main.py              # FastAPI app entry point
  config.py            # Settings (from env vars)
  database.py          # SQLAlchemy setup
  models/
    sample.py          # SalinitySample model
  routers/
    register.py        # Shipboard registration routes
    measure.py         # Lab measurement routes
  utils/
    bot_parser.py      # Seabird BOT file parser
    qr_generator.py    # QR code + label PDF generator
    physchem.py        # PhysChem API client
  templates/           # Jinja2 HTML templates
db/
  init.sql             # PostgreSQL init script
tests/
  test_bot_parser.py
```

## Configuration

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `BASE_URL` | Public URL of the app (embedded in QR codes) |
| `SECRET_KEY` | App secret key |
| `PHYSCHEM_API_URL` | IMR PhysChem API base URL |
| `PHYSCHEM_API_KEY` | PhysChem API bearer token |

## PhysChem Integration

Edit `app/utils/physchem.py` to match the actual PhysChem API payload format once you have API access. The client currently sends a generic payload — update the `payload` dict to match your spec.

## Label Printing

The app generates 62mm × 40mm PDF labels (Brother QL format).
Download from `/label/{id}/pdf` and print from any PDF-capable printer or use the Brother QL SDK for direct printing.
