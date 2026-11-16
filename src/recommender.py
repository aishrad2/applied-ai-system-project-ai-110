import csv
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class Song:
    """Represents a song and its attributes."""

    id: int
    title: str
    artist: str
    genre: str
    mood: Optional[str]
    energy: float
    tempo_bpm: float
    valence: float
    danceability: float
    acousticness: float
    track_id: Optional[str] = None
    subgenre: Optional[str] = None
    release_date: Optional[str] = None
    language: Optional[str] = None
    era: Optional[str] = None
    spotify_uri: Optional[str] = None
    loudness: Optional[float] = None


@dataclass
class UserProfile:
    """Represents a user's taste preferences."""

    favorite_genre: Optional[str] = None
    favorite_mood: Optional[str] = None
    target_energy: Optional[float] = None
    likes_acoustic: Optional[bool] = None
    favorite_artist: Optional[str] = None
    target_tempo_bpm: Optional[float] = None
    target_valence: Optional[float] = None
    target_danceability: Optional[float] = None
    target_acousticness: Optional[float] = None
    target_loudness: Optional[float] = None
    language: Optional[str] = None
    era: Optional[str] = None
    setting: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert the user profile into the preference dictionary used by scoring."""
        prefs: Dict[str, Any] = {}
        for field_name, value in asdict(self).items():
            if field_name != "likes_acoustic" and value is not None:
                prefs[field_name] = value
        if self.target_acousticness is None and self.likes_acoustic is not None:
            prefs["target_acousticness"] = float(self.likes_acoustic)
        return prefs


class Recommender:
    """OOP implementation of the recommendation logic."""

    def __init__(self, songs: List[Song]):
        self.songs = songs

    def recommend(self, user: UserProfile, k: int = 5) -> List[Song]:
        """Return the k songs with the highest similarity score for a user."""
        if k <= 0:
            return []

        song_dicts = [asdict(song) for song in self.songs]
        ranked = recommend_songs(user.to_dict(), song_dicts, k=k)
        return [Song(**song_dict) for song_dict, _, _ in ranked]

    def explain_recommendation(self, user: UserProfile, song: Song) -> str:
        """Return a human-readable explanation for why a song matches the user profile."""
        score, reasons = score_song(user.to_dict(), asdict(song))
        if not reasons:
            return "No matching preferences were provided for this song."
        return "; ".join(reasons)


def _derive_era(release_date: Optional[str]) -> Optional[str]:
    if not release_date:
        return None
    try:
        year = int(release_date[:4])
    except (TypeError, ValueError):
        return None
    if year < 1990:
        return "pre-1990"
    decade = year - year % 10
    return f"{decade}s"


def _derive_mood(energy: float, valence: float) -> str:
    if energy >= 0.5:
        return "happy" if valence >= 0.5 else "intense"
    return "calm" if valence >= 0.5 else "melancholic"


def load_songs(csv_path: str, language_labels_path: Optional[str] = None) -> List[Dict]:
    """Load the project catalog or Spotify export, deriving supported metadata."""
    numeric_fields = {
        "energy",
        "tempo_bpm",
        "valence",
        "danceability",
        "acousticness",
    }
    labels_path = Path(language_labels_path) if language_labels_path else Path("data/language_labels.csv")
    if language_labels_path and not labels_path.is_file():
        raise FileNotFoundError(f"Language labels file not found: {labels_path}")
    language_labels: Dict[str, str] = {}
    if labels_path.is_file():
        with labels_path.open(newline="", encoding="utf-8-sig") as labels_file:
            for label in csv.DictReader(labels_file):
                track_id = label.get("track_id", "").strip()
                language = label.get("language", "").strip()
                if track_id and language:
                    language_labels[track_id] = language

    with open(csv_path, newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        spotify_format = "track_id" in (reader.fieldnames or [])
        required_fields = (
            {
                "track_id", "track_name", "track_artist", "playlist_genre",
                "energy", "tempo", "valence", "danceability", "acousticness",
            }
            if spotify_format
            else {
                "id", "title", "artist", "genre", "energy", "tempo_bpm",
                "valence", "danceability", "acousticness",
            }
        )
        missing_fields = required_fields - set(reader.fieldnames or [])
        if missing_fields:
            raise ValueError(
                f"{csv_path} is missing required columns: {', '.join(sorted(missing_fields))}"
            )
        songs = []
        seen_track_ids = set()
        for row_number, row in enumerate(reader, start=1):
            if spotify_format:
                track_id = row["track_id"].strip()
                if track_id and track_id in seen_track_ids:
                    continue
                if track_id:
                    seen_track_ids.add(track_id)
                row = {
                    "id": row_number,
                    "track_id": track_id or None,
                    "spotify_uri": f"spotify:track:{track_id}" if track_id else None,
                    "title": row["track_name"],
                    "artist": row["track_artist"],
                    "genre": row["playlist_genre"],
                    "subgenre": row.get("playlist_subgenre"),
                    "mood": row.get("mood"),
                    "release_date": row.get("track_album_release_date"),
                    "language": row.get("language") or language_labels.get(track_id),
                    "energy": row["energy"],
                    "tempo_bpm": row["tempo"],
                    "valence": row["valence"],
                    "danceability": row["danceability"],
                    "acousticness": row["acousticness"],
                    "loudness": row.get("loudness"),
                }
            else:
                try:
                    row["id"] = int(row["id"])
                except ValueError as error:
                    raise ValueError(
                        f"{csv_path}: row {row_number + 1} has an invalid song id"
                    ) from error
                row["release_date"] = row.get("release_date") or row.get("track_album_release_date")
                row["language"] = row.get("language") or None
                row["spotify_uri"] = row.get("spotify_uri") or None
                row["loudness"] = row.get("loudness") or None
            for field in numeric_fields:
                try:
                    row[field] = float(row[field])
                except (TypeError, ValueError) as error:
                    raise ValueError(
                        f"{csv_path}: row {row_number + 1} has invalid {field!r}"
                    ) from error
            if row["loudness"] not in (None, ""):
                try:
                    row["loudness"] = float(row["loudness"])
                except ValueError as error:
                    raise ValueError(
                        f"{csv_path}: row {row_number + 1} has invalid 'loudness'"
                    ) from error
            else:
                row["loudness"] = None
            row["era"] = row.get("era") or _derive_era(row.get("release_date"))
            row["mood"] = row.get("mood") or _derive_mood(row["energy"], row["valence"])
            songs.append(row)

    if not songs:
        raise ValueError(f"No songs found in catalog: {csv_path}")
    return songs


def _as_user_prefs(user_prefs: Dict) -> Dict:
    if isinstance(user_prefs, UserProfile):
        return user_prefs.to_dict()
    if user_prefs is None:
        return {}
    return dict(user_prefs)


def _as_song_dict(song: Any) -> Dict:
    if isinstance(song, dict):
        return song
    if hasattr(song, "__dict__"):
        return asdict(song)
    raise TypeError(f"Expected a song dict or dataclass, received {type(song)!r}")


def score_song(user_prefs: Dict, song: Dict) -> Tuple[float, List[str]]:
    """Return a song's weighted similarity score and feature-level reasons."""
    user_prefs = _as_user_prefs(user_prefs)
    song = _as_song_dict(song)

    weights = {
        "genre": 0.15,
        "mood": 0.25,
        "energy": 0.30,
        "tempo_bpm": 0.10,
        "valence": 0.06,
        "danceability": 0.06,
        "acousticness": 0.06,
        "loudness": 0.05,
        "artist": 0.02,
    }
    preference_keys = {
        "genre": "favorite_genre",
        "mood": "favorite_mood",
        "energy": "target_energy",
        "tempo_bpm": "target_tempo_bpm",
        "valence": "target_valence",
        "danceability": "target_danceability",
        "acousticness": "target_acousticness",
        "loudness": "target_loudness",
        "artist": "favorite_artist",
    }
    categorical_features = {"genre", "mood", "artist"}

    available_weight = sum(
        weight
        for feature, weight in weights.items()
        if preference_keys[feature] in user_prefs
        and user_prefs[preference_keys[feature]] is not None
        and feature in song
        and song[feature] not in (None, "")
    )
    if available_weight == 0:
        raise ValueError("At least one taste-profile preference is required to score a song")

    weighted_similarities = []
    reasons = []

    for feature, weight in weights.items():
        preference_key = preference_keys[feature]
        if preference_key not in user_prefs or user_prefs[preference_key] is None:
            continue
        if feature not in song:
            raise ValueError(f"Song is missing the requested {feature!r} feature")

        preferred_value = user_prefs[preference_key]
        song_value = song[feature]
        if song_value is None or song_value == "":
            continue
        if feature in categorical_features:
            similarity = float(str(preferred_value).casefold() == str(song_value).casefold())
            description = f"{feature} match" if similarity else f"{feature} mismatch"
        else:
            difference = abs(float(song_value) - float(preferred_value))
            scale = {"tempo_bpm": 160.0, "loudness": 60.0}.get(feature, 1.0)
            similarity = max(0.0, 1.0 - difference / scale)
            label = {"tempo_bpm": "tempo", "loudness": "loudness"}.get(feature, feature)
            description = f"{label} similarity"

        contribution = 100.0 * weight * similarity / available_weight
        weighted_similarities.append(contribution)
        reasons.append(f"{description} (+{contribution:.1f})")

    score = sum(weighted_similarities)
    return score, reasons


def recommend_songs(user_prefs: Dict, songs: List[Dict], k: int = 5) -> List[Tuple[Dict, float, str]]:
    """Return the top k songs as (song, score, explanation) tuples."""
    if k <= 0:
        return []

    user_prefs = _as_user_prefs(user_prefs)
    recommendations = []
    for song in songs:
        score, reasons = score_song(user_prefs, song)
        recommendations.append((song, score, "; ".join(reasons)))

    recommendations.sort(key=lambda recommendation: recommendation[1], reverse=True)
    del recommendations[k:]
    return recommendations
