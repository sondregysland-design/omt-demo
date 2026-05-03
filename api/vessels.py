"""Vercel serverless function — proxies BarentsWatch AIS API for Stavanger."""

from http.server import BaseHTTPRequestHandler
import json
import os
import time
import urllib.request
import urllib.parse

_token_cache = {"token": None, "expires_at": 0}

STAVANGER_POLYGON = {
    "type": "Polygon",
    "coordinates": [[
        [5.65, 58.90],
        [5.65, 59.10],
        [6.05, 59.10],
        [6.05, 58.90],
        [5.65, 58.90],
    ]]
}


def _get_token():
    if _token_cache["token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    client_id = os.environ.get("BW_CLIENT_ID", "")
    client_secret = os.environ.get("BW_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise RuntimeError("Missing BW_CLIENT_ID / BW_CLIENT_SECRET")

    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "ais",
        "grant_type": "client_credentials",
    }).encode()

    req = urllib.request.Request(
        "https://id.barentswatch.no/connect/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read())

    _token_cache["token"] = body["access_token"]
    _token_cache["expires_at"] = time.time() + body.get("expires_in", 3600)
    return _token_cache["token"]


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            token = _get_token()
        except Exception as e:
            self._json_response(500, {"error": str(e)})
            return

        payload = json.dumps({
            "geometry": STAVANGER_POLYGON,
            "modelType": "Full",
            "modelFormat": "Json",
        }).encode()

        req = urllib.request.Request(
            "https://live.ais.barentswatch.no/v1/latest/combined",
            data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read()
            self._json_response(200, json.loads(body))
        except Exception as e:
            self._json_response(502, {"error": f"AIS API error: {e}"})

    def _json_response(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "s-maxage=15, stale-while-revalidate=30")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
