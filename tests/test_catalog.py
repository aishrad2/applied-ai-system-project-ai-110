import csv

from src.catalog import SOURCE_COLUMNS, genre_vocabulary, load_catalog


def _row(**overrides):
    row = {
        "performer": "Artist", "song": "Test Song",
        "spotify_genre": "['pop', 'dance pop']", "spotify_track_id": "id-1",
        "spotify_track_duration_ms": "180000", "spotify_track_explicit": "False",
        "spotify_track_album": "Album", "danceability": ".5", "energy": ".5",
        "key": "4", "loudness": "-8", "mode": "1", "speechiness": ".05",
        "acousticness": ".4", "instrumentalness": ".1", "liveness": ".1",
        "valence": ".5", "tempo": "100", "spotify_track_popularity": "40",
        "peak_position": "10", "weeks_on_chart": "5", "first_week": "2018-01-01",
    }
    return {**row, **overrides}


def _write(path, rows):
    columns = list(SOURCE_COLUMNS) + ["unapproved_column"]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows({**row, "unapproved_column": "ignored"} for row in rows)


def test_catalog_drops_incomplete_deduplicates_and_derives_labels(tmp_path, caplog):
    path = tmp_path / "songs.csv"
    _write(path, [
        _row(),
        _row(song="duplicate"),
        _row(spotify_track_id="", song="missing id"),
        _row(spotify_track_id="missing-audio", energy=""),
        _row(spotify_track_id="old", first_week="1965-01-01", energy=".2", valence=".2"),
        _row(spotify_track_id="unknown-era", first_week=""),
    ])

    with caplog.at_level("INFO", logger="src.catalog"):
        songs = load_catalog(path)

    assert len(songs) == 3
    assert songs[0]["mood"] == "happy/hype"
    assert songs[0]["era"] == "2010s"
    assert songs[1]["mood"] == "sad/mellow"
    assert songs[1]["era"] == "1950s-60s"
    assert songs[2]["era"] == "any"
    assert songs[0]["spotify_uri"] == "spotify:track:id-1"
    assert genre_vocabulary(songs) == ["dance pop", "pop"]
    assert "dropped_incomplete=2 duplicates=1 kept=3" in caplog.text
