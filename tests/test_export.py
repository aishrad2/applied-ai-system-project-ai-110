import csv
import io

from src.export import csv_bytes


def test_csv_exports_requested_columns_direct_links_and_formula_safety():
    tracks = [{
        "track_id": "abc123", "title": "=cmd", "artist": "+Artist",
        "score": 87.5, "breakdown": {"mood": 20.0},
    }]
    rows = list(csv.DictReader(io.StringIO(csv_bytes(tracks).decode())))

    assert rows[0]["spotify_track_id"] == "abc123"
    assert rows[0]["song"] == "'=cmd"
    assert rows[0]["performer"] == "'+Artist"
    assert rows[0]["spotify_url"] == "https://open.spotify.com/track/abc123"
    assert set(rows[0]) == {
        "spotify_track_id", "song", "performer", "score", "reason", "spotify_url",
    }
