import csv
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import quote_plus

from .recommender import recommend_songs


MOODS = {
    "happy": (0.75, 0.85),
    "calm": (0.30, 0.70),
    "intense": (0.85, 0.30),
    "melancholic": (0.30, 0.25),
}
SETTINGS = {
    "commute": {},
    "studying": {"target_energy": 0.35, "target_tempo_bpm": 85.0},
    "workout": {"target_energy": 0.90, "target_tempo_bpm": 130.0},
    "party": {"target_energy": 0.85, "target_danceability": 0.85},
    "relaxing": {"target_energy": 0.25, "target_acousticness": 0.75},
}
ALLOWED_NOTE_PREFERENCES = {
    "favorite_genre",
    "favorite_artist",
    "target_energy",
    "target_tempo_bpm",
    "target_valence",
    "target_danceability",
    "target_acousticness",
    "target_loudness",
}
GENRES = (
    "edm", "rap", "pop", "r&b", "latin", "rock", "lofi", "jazz",
    "folk", "country", "classical", "reggae", "metal", "electronic",
)


@dataclass
class PlaylistRequest:
    mood: str
    language: str = "any"
    era: str = "any"
    setting: str = "commute"
    notes: str = ""
    count: int = 10


@dataclass
class Verification:
    passed: bool
    issues: List[str]


@dataclass
class PlaylistResult:
    request: PlaylistRequest
    profile: Dict
    recommendations: List[Tuple[Dict, float, str]]
    verification: Verification
    attempts: int
    playlist_name: str


def sanitize_text(text: str, max_length: int = 500) -> str:
    cleaned = "".join(
        character
        for character in str(text)
        if unicodedata.category(character) not in {"Cc", "Cf"}
    )
    return cleaned.strip()[:max_length]


def parse_notes_keywords(notes: str) -> Dict:
    text = sanitize_text(notes).casefold()
    preferences: Dict = {}

    genre = next((item for item in GENRES if re.search(rf"\b{re.escape(item)}\b", text)), None)
    if genre:
        preferences["favorite_genre"] = genre

    artist_match = re.search(r"\bartist\s*:\s*([^,;\n]+)", text)
    if artist_match:
        preferences["favorite_artist"] = artist_match.group(1).strip()[:80]

    if re.search(r"\b(hype|energetic|high energy|upbeat)\b", text):
        preferences["target_energy"] = 0.85
    elif re.search(r"\b(chill|relaxing|mellow|low energy)\b", text):
        preferences["target_energy"] = 0.30

    if re.search(r"\b(not too slow|nothing too slow|faster|up-tempo)\b", text):
        preferences["target_tempo_bpm"] = 120.0
    elif re.search(r"\b(slow|downtempo)\b", text):
        preferences["target_tempo_bpm"] = 75.0

    if re.search(r"\b(acoustic|unplugged)\b", text):
        preferences["target_acousticness"] = 0.80
    if re.search(r"\b(danceable|dance music)\b", text):
        preferences["target_danceability"] = 0.80
    if re.search(r"\b(no loud|not loud|quiet)\b", text):
        preferences["target_loudness"] = -20.0

    return preferences


def build_profile(
    request: PlaylistRequest,
    notes_preferences: Optional[Dict] = None,
    ignore_note_energy: bool = False,
) -> Dict:
    mood = request.mood.casefold().strip()
    setting = request.setting.casefold().strip()
    if mood not in MOODS:
        raise ValueError(f"Mood must be one of: {', '.join(MOODS)}")
    if setting not in SETTINGS:
        raise ValueError(f"Setting must be one of: {', '.join(SETTINGS)}")
    if not 1 <= request.count <= 50:
        raise ValueError("Playlist length must be between 1 and 50 songs")

    energy, valence = MOODS[mood]
    profile = {
        "favorite_mood": mood,
        "target_energy": energy,
        "target_valence": valence,
        "language": request.language.casefold().strip() or "any",
        "era": request.era.casefold().strip() or "any",
        "setting": setting,
        "target_tempo_bpm": None,
        "target_danceability": None,
        "target_acousticness": None,
        "target_loudness": None,
    }
    profile.update(SETTINGS[setting])

    allowed_notes = {
        key: value
        for key, value in (notes_preferences or {}).items()
        if key in ALLOWED_NOTE_PREFERENCES
    }
    if ignore_note_energy:
        allowed_notes.pop("target_energy", None)
    profile.update(allowed_notes)
    return profile


def find_conflicts(request: PlaylistRequest) -> List[str]:
    notes = sanitize_text(request.notes).casefold()
    if request.mood in {"calm", "melancholic"} and re.search(
        r"\b(hype|energetic|high energy|workout)\b", notes
    ):
        return ["The selected mood is low-energy, but the notes ask for high energy."]
    if request.mood in {"happy", "intense"} and re.search(
        r"\b(chill|relaxing|mellow|low energy)\b", notes
    ):
        return ["The selected mood is high-energy, but the notes ask for a mellow playlist."]
    return []


def validate_request(request: PlaylistRequest) -> None:
    if request.mood.casefold().strip() not in MOODS:
        raise ValueError(f"Mood must be one of: {', '.join(MOODS)}")
    if request.setting.casefold().strip() not in SETTINGS:
        raise ValueError(f"Setting must be one of: {', '.join(SETTINGS)}")
    if not 1 <= request.count <= 50:
        raise ValueError("Playlist length must be between 1 and 50 songs")
    if request.era.casefold() != "any" and not re.fullmatch(
        r"(?:pre-1990|(?:19|20)\d0s)", request.era.casefold().strip()
    ):
        raise ValueError("Era must be 'any', 'pre-1990', or a decade such as '2010s'")
    if len(request.notes) > 500:
        raise ValueError("Notes must be 500 characters or fewer")


def verify_playlist(
    selected: Sequence[Dict],
    catalog: Sequence[Dict],
    request: PlaylistRequest,
) -> Verification:
    issues: List[str] = []
    catalog_ids = {song.get("id") for song in catalog}
    seen = set()

    if len(selected) != request.count:
        issues.append(f"Expected {request.count} songs but found {len(selected)}.")

    for song in selected:
        song_id = song.get("id")
        if song_id not in catalog_ids:
            issues.append(f"Song {song.get('title', '<unknown>')} is not in the catalog.")
        unique_id = song.get("track_id") or song_id
        if unique_id in seen:
            issues.append(f"Duplicate song: {song.get('title', '<unknown>')}.")
        seen.add(unique_id)

        if request.language.casefold() != "any":
            language = (song.get("language") or "").casefold()
            if not language or language != request.language.casefold():
                issues.append(
                    f"{song.get('title', '<unknown>')} has no verified "
                    f"{request.language} language label."
                )
        if request.era.casefold() != "any" and song.get("era") != request.era:
            issues.append(
                f"{song.get('title', '<unknown>')} does not match era {request.era}."
            )

    return Verification(not issues, issues)


def explain_recommendation(song: Dict, score: float, reasons: str) -> str:
    detail = reasons or "matched the available taste preferences"
    return (
        f"{song.get('title', 'Unknown title')} by {song.get('artist', 'Unknown artist')} "
        f"scored {score:.1f}/100 because it {detail}."
    )


def explain_playlist(result: PlaylistResult) -> List[str]:
    explanations = [
        explain_recommendation(song, score, reasons)
        for song, score, reasons in result.recommendations
    ]
    return explanations


class PlaylistAgent:
    def __init__(self, songs: Sequence[Dict], logger: Optional[logging.Logger] = None):
        self.songs = list(songs)
        self.logger = logger or logging.getLogger(__name__)

    def create(
        self,
        request: PlaylistRequest,
        notes_preferences: Optional[Dict] = None,
        ignore_note_energy: bool = False,
    ) -> PlaylistResult:
        validate_request(request)
        profile = build_profile(request, notes_preferences, ignore_note_energy)
        scoring_profile = {
            key: value
            for key, value in profile.items()
            if key not in {"language", "era", "setting"} and value is not None
        }
        ranked = recommend_songs(scoring_profile, self.songs, k=len(self.songs))
        excluded_ids = set()
        chosen: List[Tuple[Dict, float, str]] = []
        verification = Verification(False, ["Playlist has not been verified."])
        attempts = 0

        for attempts in range(1, 4):
            batch = [
                item for item in ranked
                if item[0].get("id") not in excluded_ids
            ][: request.count]
            chosen = batch
            verification = verify_playlist(
                [song for song, _, _ in chosen], self.songs, request
            )
            self.logger.info(
                "playlist attempt=%d selected=%d passed=%s issues=%s",
                attempts,
                len(chosen),
                verification.passed,
                verification.issues,
            )
            if verification.passed:
                break
            excluded_ids.update(song.get("id") for song, _, _ in chosen)

        if not verification.passed:
            chosen = ranked[: request.count]
            verification = verify_playlist(
                [song for song, _, _ in chosen], self.songs, request
            )
            if not verification.passed:
                self.logger.warning(
                    "Returning closest playlist after %d attempts: %s",
                    attempts,
                    verification.issues,
                )

        name_parts = [request.mood.title()]
        if request.era.casefold() != "any":
            name_parts.append(request.era)
        name_parts.append(request.setting.title())
        name = " ".join(name_parts) + " Mix"
        return PlaylistResult(request, profile, chosen, verification, attempts, name)


def configure_logging(log_path: str = "logs/run.log") -> logging.Logger:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("playlist_pilot")
    logger.setLevel(logging.INFO)
    if not any(getattr(handler, "baseFilename", None) == str(path.resolve()) for handler in logger.handlers):
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


def _csv_safe(value: object) -> str:
    text = str(value if value is not None else "")
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


def export_csv(result: PlaylistResult, path: str = "playlist.csv") -> None:
    with open(path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=(
                "title", "artist", "genre", "mood", "era", "language",
                "score", "reason", "search_url",
            ),
        )
        writer.writeheader()
        for song, score, reasons in result.recommendations:
            query = quote_plus(f"{song.get('title', '')} {song.get('artist', '')}")
            writer.writerow(
                {
                    "title": _csv_safe(song.get("title")),
                    "artist": _csv_safe(song.get("artist")),
                    "genre": _csv_safe(song.get("genre")),
                    "mood": _csv_safe(song.get("mood")),
                    "era": _csv_safe(song.get("era")),
                    "language": _csv_safe(song.get("language")),
                    "score": f"{score:.2f}",
                    "reason": _csv_safe(explain_recommendation(song, score, reasons)),
                    "search_url": f"https://open.spotify.com/search/{query}",
                }
            )


def fixed_profile_tests(songs: Sequence[Dict]) -> List[Dict[str, object]]:
    profiles = [
        PlaylistRequest("happy", setting="party", count=5),
        PlaylistRequest("calm", setting="studying", count=5),
        PlaylistRequest("intense", setting="workout", count=5),
        PlaylistRequest("melancholic", setting="relaxing", count=5),
    ]
    results = []
    agent = PlaylistAgent(songs)
    for index, request in enumerate(profiles, start=1):
        first = agent.create(request)
        second = agent.create(request)
        first_ids = [song.get("id") for song, _, _ in first.recommendations]
        second_ids = [song.get("id") for song, _, _ in second.recommendations]
        results.append(
            {
                "profile": f"profile-{index}",
                "verified": first.verification.passed,
                "songs": len(first.recommendations),
                "deterministic": first_ids == second_ids,
                "issues": "; ".join(first.verification.issues),
            }
        )
    return results


def format_test_results(results: Sequence[Dict[str, object]]) -> str:
    header = f"{'Profile':<12} {'Verified':<10} {'Songs':<7} {'Deterministic':<14} Issues"
    lines = [header, "-" * len(header)]
    for item in results:
        lines.append(
            f"{item['profile']:<12} {str(item['verified']):<10} "
            f"{item['songs']:<7} {str(item['deterministic']):<14} {item['issues']}"
        )
    return "\n".join(lines)
