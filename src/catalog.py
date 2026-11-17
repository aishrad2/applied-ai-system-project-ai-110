import ast
import logging

import pandas as pd


SOURCE_COLUMNS = {
    "performer", "song", "spotify_genre", "spotify_track_id",
    "spotify_track_duration_ms", "spotify_track_explicit",
    "spotify_track_album", "danceability", "energy", "key", "loudness",
    "mode", "speechiness", "acousticness", "instrumentalness", "liveness",
    "valence", "tempo", "spotify_track_popularity", "peak_position",
    "weeks_on_chart", "first_week",
}
FEATURES = (
    "energy", "tempo", "valence", "danceability", "acousticness",
    "speechiness", "instrumentalness", "liveness", "loudness",
)
REQUIRED = (
    "spotify_track_id", "spotify_track_duration_ms", *FEATURES,
)


def _tags(value):
    try:
        parsed = ast.literal_eval(value)
    except (ValueError, SyntaxError, TypeError):
        parsed = [value] if isinstance(value, str) else []
    if not isinstance(parsed, (list, tuple)):
        return []
    return list(dict.fromkeys(
        item.strip().casefold() for item in parsed
        if isinstance(item, str) and item.strip()
    ))


def load_catalog(path):
    frame = pd.read_csv(
        path,
        usecols=lambda column: column in SOURCE_COLUMNS,
        dtype={"spotify_track_id": "string"},
    )
    rows_read = len(frame)
    for column in ("spotify_track_duration_ms", *FEATURES):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    missing = frame[list(REQUIRED)].isna().any(axis=1)
    missing |= frame["spotify_track_id"].fillna("").str.strip().eq("")
    dropped = int(missing.sum())
    frame = frame.loc[~missing].copy()
    before_dedupe = len(frame)
    frame["spotify_track_id"] = frame["spotify_track_id"].str.strip()
    frame = frame.drop_duplicates("spotify_track_id", keep="first").copy()
    duplicates = before_dedupe - len(frame)

    year = pd.to_numeric(
        frame["first_week"].astype("string").str.slice(0, 4), errors="coerce"
    )
    decades = (year // 10 * 10).astype("Int64").astype("string") + "s"
    frame["era"] = decades.where(year >= 1970, "1950s-60s").where(year.notna(), "any")
    frame["mood"] = "happy/hype"
    frame.loc[(frame.valence < .5) & (frame.energy < .5), "mood"] = "sad/mellow"
    frame.loc[(frame.valence < .5) & (frame.energy >= .5), "mood"] = "intense/angry"
    frame.loc[(frame.valence >= .5) & (frame.energy < .5), "mood"] = "chill/peaceful"
    frame["genre_tags"] = frame["spotify_genre"].map(_tags)

    songs = []
    for row in frame.to_dict("records"):
        track_id = row["spotify_track_id"]
        songs.append({
            "track_id": track_id,
            "spotify_uri": f"spotify:track:{track_id}",
            "title": str(row["song"]) if pd.notna(row["song"]) else "",
            "artist": str(row["performer"]) if pd.notna(row["performer"]) else "",
            "genre_tags": row["genre_tags"],
            "era": row["era"],
            "mood": row["mood"],
            "duration_ms": int(row["spotify_track_duration_ms"]),
            **{feature: float(row[feature]) for feature in FEATURES},
        })

    logging.getLogger(__name__).info(
        "catalog rows=%d dropped_incomplete=%d duplicates=%d kept=%d",
        rows_read, dropped, duplicates, len(songs),
    )
    if not songs:
        raise ValueError(f"No complete songs found in {path}")
    return songs


def genre_vocabulary(songs):
    return sorted({tag for song in songs for tag in song["genre_tags"]})
