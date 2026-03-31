# APRS Map

A personal web app for displaying APRS station data on multiple map overlays — including topographic, satellite, and outdoor layers — using the [aprs.fi](https://aprs.fi) API.

Built by KH7AL. Hosted at [aprs.ops-relay.co](https://aprs.ops-relay.co).

## Map Layers

| Layer | Source | API Key Required |
|---|---|---|
| OpenStreetMap | openstreetmap.org | No |
| Topo — OpenTopoMap | opentopomap.org | No |
| Topo — USGS | nationalmap.gov | No |
| Satellite — ESRI | arcgisonline.com | No |
| MapTiler Outdoor | maptiler.com | Yes (free tier) |

## Setup

### 1. aprs.fi API Key

1. Create a free account at [aprs.fi](https://aprs.fi)
2. Go to **My account → API keys** and generate a key

### 2. MapTiler API Key (optional)

Required only for the MapTiler Outdoor layer.

1. Create a free account at [maptiler.com](https://www.maptiler.com/)
2. Go to **Account → API keys** and copy your default key
3. Free tier: 100,000 tile requests/month

### 3. Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```
APRS_API_KEY=your_aprs_fi_key
MAPTILER_API_KEY=your_maptiler_key   # optional
OPERATOR_CALLSIGN=KH7AL
CACHE_TTL=300
```

### 4. Run Locally

```bash
pip install -r requirements.txt
cp .env.example .env   # then edit .env
flask run
```

## Deploying to Render

1. Push this repo to GitHub
2. Create a new **Web Service** on [render.com](https://render.com) pointed at the repo
3. Set the following:
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `gunicorn --workers 2 --bind 0.0.0.0:$PORT app:app`
4. Add environment variables in the Render dashboard (same as `.env` above)

## Data & Attribution

APRS position data is fetched live from the [aprs.fi API](https://aprs.fi/page/api).
Amateur radio transmissions are public domain per FCC rules.
This app is for personal, non-commercial use only.
