import base64
import csv
import hashlib
import io
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer


def csv_bytes(tracks):
    output = io.StringIO(newline="")
    columns = ("spotify_track_id", "song", "performer", "score", "reason", "spotify_url")
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    for track in tracks:
        safe = lambda value: "'" + str(value) if str(value).startswith(("=", "+", "-", "@")) else str(value or "")
        track_id = track["track_id"]
        reason = ", ".join(f"{key} +{value:.1f}" for key, value in track["breakdown"].items())
        writer.writerow({
            "spotify_track_id": safe(track_id), "song": safe(track["title"]),
            "performer": safe(track["artist"]), "score": f"{track['score']:.2f}",
            "reason": safe(reason),
            "spotify_url": f"https://open.spotify.com/track/{track_id}",
        })
    return output.getvalue().encode("utf-8")


def _api(method, url, token, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url, data=data, method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            content = response.read()
            return json.loads(content.decode()) if content else {}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Spotify request failed: {type(error).__name__}") from error


def export_spotify(tracks, name):
    client_id = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
    redirect = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
    parsed = urllib.parse.urlparse(redirect)
    if not client_id or parsed.hostname != "127.0.0.1" or not parsed.port:
        raise RuntimeError("Set SPOTIFY_CLIENT_ID and a registered 127.0.0.1 redirect URI.")

    verifier, state = secrets.token_urlsafe(64), secrets.token_urlsafe(24)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    callback = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            callback.update(state=query.get("state", [""])[0], code=query.get("code", [""])[0])
            self.send_response(200 if callback["code"] else 400)
            self.end_headers()
            self.wfile.write(b"Spotify authorization received. You can close this tab.")
        def log_message(self, fmt, *args):
            return

    query = urllib.parse.urlencode({
        "client_id": client_id, "response_type": "code", "redirect_uri": redirect,
        "scope": "playlist-modify-private", "state": state,
        "code_challenge_method": "S256", "code_challenge": challenge,
    })
    server = HTTPServer((parsed.hostname, parsed.port), Handler)
    server.timeout = 1
    try:
        webbrowser.open("https://accounts.spotify.com/authorize?" + query)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline and not callback:
            server.handle_request()
    finally:
        server.server_close()
    if callback.get("state") != state or not callback.get("code"):
        raise RuntimeError("Spotify authorization was cancelled or timed out.")

    form = urllib.parse.urlencode({
        "client_id": client_id, "grant_type": "authorization_code",
        "code": callback["code"], "redirect_uri": redirect,
        "code_verifier": verifier,
    }).encode()
    request = urllib.request.Request(
        "https://accounts.spotify.com/api/token", data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            token = json.loads(response.read().decode())["access_token"]
    except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Spotify token exchange failed: {type(error).__name__}") from error

    playlist = _api("POST", "https://api.spotify.com/v1/me/playlists", token, {
        "name": name, "description": "Built by Playlist Pilot.", "public": False,
    })
    playlist_id = playlist.get("id")
    if not playlist_id:
        raise RuntimeError("Spotify did not return a playlist ID.")
    uris = [track["spotify_uri"] for track in tracks]
    for start in range(0, len(uris), 100):
        _api("POST", f"https://api.spotify.com/v1/playlists/{playlist_id}/items", token,
             {"uris": uris[start:start + 100]})
    return playlist.get("external_urls", {}).get("spotify", "")
