#!/usr/bin/env python3
"""
APRS Map — Display APRS station data on configurable map overlays.
Callsign search via aprs.fi API; area view via direct APRS-IS connection.
Personal non-commercial use by KH7AL.
"""

import math
import os
import time
import threading

import aprslib
import requests
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

APRS_API_BASE = "https://api.aprs.fi/api/get"
APRS_API_KEY  = os.environ.get("APRS_API_KEY", "")
MAPTILER_KEY  = os.environ.get("MAPTILER_API_KEY", "")
CALLSIGN      = os.environ.get("OPERATOR_CALLSIGN", "KH7AL")
CACHE_TTL     = int(os.environ.get("CACHE_TTL", 300))

APP_VERSION = "1.0"
APP_REPO    = "github.com/alevie76-dev/aprs-map"
USER_AGENT  = f"APRS-Map/{APP_VERSION} {APP_REPO} {CALLSIGN}"

STATION_TTL  = 1800   # drop stations not heard for 30 min
DEFAULT_LAT  = 20.5
DEFAULT_LNG  = -157.5
DEFAULT_DIST = 200    # km — initial APRS-IS filter radius

# ── aprs.fi callsign-lookup cache ─────────────────────────────────────────────

_aprsfi_cache: dict = {}
_aprsfi_lock = threading.Lock()


def fetch_aprs(params: dict) -> dict:
    cache_key = str(sorted(params.items()))
    with _aprsfi_lock:
        entry = _aprsfi_cache.get(cache_key)
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

    with _aprsfi_lock:
        _aprsfi_cache[cache_key] = {"data": data, "ts": time.time()}

    return data


# ── APRS-IS direct connection ─────────────────────────────────────────────────

_stations: dict = {}          # callsign → station dict
_stations_lock = threading.Lock()
_aprs_is: aprslib.IS | None = None
_current_filter = f"r/{DEFAULT_LAT}/{DEFAULT_LNG}/{DEFAULT_DIST}"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def on_packet(packet: dict) -> None:
    try:
        if "latitude" not in packet or "longitude" not in packet:
            return
        # Map aprslib type to our type codes
        fmt = packet.get("format", "")
        ptype = "w" if fmt == "wx" else "l"
        with _stations_lock:
            _stations[packet["from"]] = {
                "name":      packet["from"],
                "type":      ptype,
                "lat":       str(packet["latitude"]),
                "lng":       str(packet["longitude"]),
                "comment":   packet.get("comment", ""),
                "symbol":    (packet.get("symbol_table", "") or "") + (packet.get("symbol", "") or ""),
                "lasttime":  str(int(time.time())),
                "speed":     str(packet.get("speed") or 0),
                "course":    str(packet.get("course") or 0),
                "altitude":  str(packet.get("altitude") or 0),
            }
    except Exception:
        pass


def aprs_is_worker() -> None:
    global _aprs_is, _current_filter
    while True:
        try:
            app.logger.info(f"APRS-IS connecting (filter: {_current_filter})")
            _aprs_is = aprslib.IS(
                CALLSIGN,
                passwd=-1,
                host="rotate.aprs.net",
                port=14580,
                appid=f"APRS-Map {APP_VERSION}",
            )
            _aprs_is.set_filter(_current_filter)
            _aprs_is.connect()
            _aprs_is.consumer(on_packet, raw=False)
        except Exception as e:
            app.logger.warning(f"APRS-IS disconnected: {e} — reconnecting in 15 s")
            _aprs_is = None
            time.sleep(15)


def update_aprs_filter(lat: float, lng: float, dist: float) -> None:
    global _current_filter
    new_filter = f"r/{lat:.4f}/{lng:.4f}/{int(dist)}"
    if new_filter == _current_filter:
        return
    _current_filter = new_filter
    conn = _aprs_is
    if conn is not None:
        try:
            conn.sendall(f"#filter {new_filter}\r\n")
        except Exception:
            pass  # worker will reconnect with the updated _current_filter


# Start APRS-IS listener in background
threading.Thread(target=aprs_is_worker, daemon=True, name="aprs-is").start()


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template(
        "index.html",
        maptiler_key=MAPTILER_KEY,
        default_callsign=CALLSIGN,
    )


@app.route("/api/status")
def api_status():
    with _stations_lock:
        count = len(_stations)
    return jsonify({
        "aprs_is_connected": _aprs_is is not None,
        "current_filter":    _current_filter,
        "stations_buffered": count,
    })


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
    """Return buffered APRS-IS stations within dist km of lat/lng."""
    try:
        lat  = float(request.args.get("lat", ""))
        lng  = float(request.args.get("lng", ""))
        dist = min(float(request.args.get("dist", 50)), 200)
    except (TypeError, ValueError):
        return jsonify({"error": "lat, lng, and dist (km) are required"}), 400

    update_aprs_filter(lat, lng, dist)

    now = time.time()
    results = []
    with _stations_lock:
        for station in list(_stations.values()):
            try:
                if now - float(station["lasttime"]) > STATION_TTL:
                    continue
                if haversine_km(lat, lng, float(station["lat"]), float(station["lng"])) <= dist:
                    results.append(station)
            except Exception:
                continue

    return jsonify({"result": "ok", "found": len(results), "entries": results})


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
