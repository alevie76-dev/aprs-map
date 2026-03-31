#!/usr/bin/env python3
"""
APRS Map — Display APRS station data on configurable map overlays.
Data sourced from the aprs.fi API (https://aprs.fi/page/api).
Personal non-commercial use by KH7AL.
"""

import os
import time
import threading

import requests
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

APRS_API_BASE = "https://api.aprs.fi/api/get"
APRS_API_KEY  = os.environ.get("APRS_API_KEY", "")
MAPTILER_KEY  = os.environ.get("MAPTILER_API_KEY", "")
CALLSIGN      = os.environ.get("OPERATOR_CALLSIGN", "KH7AL")
CACHE_TTL     = int(os.environ.get("CACHE_TTL", 300))  # seconds; default 5 min

APP_VERSION = "1.0"
APP_REPO    = "github.com/alevie76-dev/aprs-map"
USER_AGENT  = f"APRS-Map/{APP_VERSION} {APP_REPO} {CALLSIGN}"

_cache: dict = {}
_lock = threading.Lock()


def fetch_aprs(params: dict) -> dict:
    """Fetch from aprs.fi API with server-side caching."""
    cache_key = str(sorted(params.items()))
    with _lock:
        entry = _cache.get(cache_key)
        if entry and (time.time() - entry["ts"]) < CACHE_TTL:
            return entry["data"]

    query = {**params, "apikey": APRS_API_KEY, "format": "json"}
    resp = requests.get(
        APRS_API_BASE,
        params=query,
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    with _lock:
        _cache[cache_key] = {"data": data, "ts": time.time()}

    return data


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template(
        "index.html",
        maptiler_key=MAPTILER_KEY,
        default_callsign=CALLSIGN,
    )


@app.route("/api/location")
def api_location():
    name = request.args.get("name", "").strip().upper()
    if not name:
        return jsonify({"error": "name parameter required"}), 400
    if not APRS_API_KEY:
        return jsonify({"error": "APRS_API_KEY not configured on server"}), 500
    try:
        return jsonify(fetch_aprs({"name": name, "what": "loc"}))
    except requests.HTTPError as e:
        return jsonify({"error": f"aprs.fi returned HTTP {e.response.status_code}"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/area")
def api_area():
    """Return all APRS stations within `dist` km of lat/lng."""
    try:
        lat  = float(request.args.get("lat", ""))
        lng  = float(request.args.get("lng", ""))
        dist = float(request.args.get("dist", 50))
    except (TypeError, ValueError):
        return jsonify({"error": "lat, lng, and dist (km) are required"}), 400

    dist = min(dist, 200)  # cap to protect API quota

    if not APRS_API_KEY:
        return jsonify({"error": "APRS_API_KEY not configured on server"}), 500
    try:
        return jsonify(fetch_aprs({"what": "loc", "lat": lat, "lng": lng, "dist": dist}))
    except requests.HTTPError as e:
        return jsonify({"error": f"aprs.fi returned HTTP {e.response.status_code}"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/weather")
def api_weather():
    name = request.args.get("name", "").strip().upper()
    if not name:
        return jsonify({"error": "name parameter required"}), 400
    if not APRS_API_KEY:
        return jsonify({"error": "APRS_API_KEY not configured on server"}), 500
    try:
        return jsonify(fetch_aprs({"name": name, "what": "wx"}))
    except requests.HTTPError as e:
        return jsonify({"error": f"aprs.fi returned HTTP {e.response.status_code}"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
