"""Interactive Playlist Pilot CLI."""

import argparse
import logging
from pathlib import Path
from typing import Dict, Iterable, Optional

from .integrations import (
    LLMError,
    SpotifyExportError,
    load_dotenv,
    llm_note_preferences,
    make_llm_client,
    make_spotify_exporter,
)
from .playlist_agent import (
    MOODS,
    SETTINGS,
    PlaylistAgent,
    PlaylistRequest,
    configure_logging,
    explain_playlist,
    export_csv,
    find_conflicts,
    fixed_profile_tests,
    format_test_results,
    parse_notes_keywords,
    sanitize_text,
)
from .recommender import load_songs


def _ask_choice(prompt: str, options: Iterable[str], default: str) -> str:
    allowed = [option for option in options]
    while True:
        answer = input(f"{prompt} ({'/'.join(allowed)}) [{default}]: ").strip()
        if not answer:
            return default
        normalized = answer.casefold()
        if normalized in {option.casefold() for option in allowed}:
            return normalized
        print(f"Choose one of: {', '.join(allowed)}")


def _collect_request(songs, count: int) -> PlaylistRequest:
    languages = sorted(
        {song["language"].casefold() for song in songs if song.get("language")}
    )
    eras = sorted({song["era"] for song in songs if song.get("era")})
    print("\nPlaylist Pilot — describe the playlist you want.")
    if languages:
        print(f"Catalog language labels: {', '.join(languages)}")
    else:
        print("This catalog has no language labels; choose 'any' for unfiltered results.")
    mood = _ask_choice("Mood", MOODS, "happy")
    language_options = ["any"] + languages
    language = _ask_choice("Language", language_options, "any")
    era = _ask_choice("Era", ["any"] + eras, "any")
    setting = _ask_choice("Setting", SETTINGS, "commute")
    raw_notes = input("Optional notes (max 500 characters): ")
    if len(raw_notes) > 500:
        raise ValueError("Notes must be 500 characters or fewer.")
    notes = sanitize_text(raw_notes)
    return PlaylistRequest(
        mood=mood,
        language=language,
        era=era,
        setting=setting,
        notes=notes,
        count=count,
    )


def _resolve_conflicts(request: PlaylistRequest) -> bool:
    conflicts = find_conflicts(request)
    if not conflicts:
        return False
    print("\nI found a possible conflict:")
    for conflict in conflicts:
        print(f"- {conflict}")
    choice = _ask_choice("Which should take priority?", ["quiz", "notes"], "quiz")
    return choice == "quiz"


def _print_playlist(result, explanations) -> None:
    print(f"\n{result.playlist_name}")
    print("=" * len(result.playlist_name))
    print(f"Verifier: {'PASS' if result.verification.passed else 'BEST-EFFORT / ISSUES'}")
    print(f"Attempts: {result.attempts}/3")
    for issue in result.verification.issues:
        print(f"Warning: {issue}")
    for index, ((song, score, _), explanation) in enumerate(
        zip(result.recommendations, explanations), start=1
    ):
        print(f"\n{index}. {song.get('title')} — {song.get('artist')} ({score:.1f}/100)")
        print(f"   {explanation}")


def _self_test(csv_path: str, language_labels_path: Optional[str], logger: logging.Logger) -> int:
    songs = load_songs(csv_path, language_labels_path)
    results = fixed_profile_tests(songs)
    print(format_test_results(results))
    verified = sum(bool(result["verified"]) for result in results)
    deterministic = sum(bool(result["deterministic"]) for result in results)
    print(f"\nVerifier pass rate: {verified}/{len(results)}")
    print(f"Repeatability: {deterministic}/{len(results)}")
    logger.info(
        "self_test profiles=%d verified=%d deterministic=%d",
        len(results),
        verified,
        deterministic,
    )
    return 0 if verified == len(results) and deterministic == len(results) else 1


def run_agent(
    csv_path: str,
    language_labels_path: Optional[str] = None,
    export_target: str = "csv",
    count: int = 10,
) -> int:
    logger = configure_logging()
    try:
        load_dotenv()
        songs = load_songs(csv_path, language_labels_path)
        logger.info("catalog_loaded path=%s songs=%d", csv_path, len(songs))
        llm = make_llm_client(logger)
        request = _collect_request(songs, count)
        ignore_note_energy = _resolve_conflicts(request)

        note_preferences: Dict = parse_notes_keywords(request.notes)
        llm_preferences = llm_note_preferences(request.notes, llm, logger)
        note_preferences.update(llm_preferences)

        agent = PlaylistAgent(songs, logger)
        result = agent.create(
            request,
            notes_preferences=note_preferences,
            ignore_note_energy=ignore_note_energy,
        )
        try:
            ai_explanation = llm.explain(result)
        except LLMError as error:
            logger.warning("%s Falling back to deterministic explanations.", error)
            print(f"{error} Falling back to deterministic explanations.")
            ai_explanation = None
        if ai_explanation:
            result.playlist_name = ai_explanation["playlist_name"]
            explanations = ai_explanation["reasons"]
        else:
            explanations = explain_playlist(result)
        _print_playlist(result, explanations)

        approval = _ask_choice(
            "Approve this playlist for export?", ["yes", "no"], "no"
        )
        if approval != "yes":
            logger.info("playlist_export_declined")
            print("Nothing was exported.")
            return 0

        export_csv(result, "playlist.csv")
        logger.info("csv_exported path=playlist.csv")
        print("Saved playlist.csv with Spotify search links.")
        if export_target == "spotify":
            try:
                spotify_url = make_spotify_exporter().export(result)
            except SpotifyExportError as error:
                logger.error("Spotify export failed: %s", error)
                print(f"Spotify export failed: {error}")
                print("The approved CSV and search links are available as playlist.csv.")
            else:
                logger.info("spotify_exported url=%s", spotify_url)
                print(f"Created Spotify playlist: {spotify_url}")
        return 0
    except (LLMError, ValueError, OSError) as error:
        logger.error("playlist_run_failed: %s", error)
        print(f"Could not create playlist: {error}")
        return 1


def _default_catalog() -> str:
    if Path("data/spotify_songs.csv").is_file():
        return "data/spotify_songs.csv"
    return "data/songs.csv"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and verify a personalized playlist.")
    parser.add_argument("--csv", default=_default_catalog(), help="song catalog CSV")
    parser.add_argument(
        "--language-labels",
        default=None,
        help="optional CSV with track_id,language columns for manual language labels",
    )
    parser.add_argument(
        "--export",
        choices=("csv", "spotify"),
        default="csv",
        help="export locally or also create a Spotify playlist after approval",
    )
    parser.add_argument("--count", type=int, default=10, help="playlist size from 1 to 50")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run deterministic reliability profiles without calling Gemini",
    )
    arguments = parser.parse_args()
    logger = configure_logging()
    try:
        if arguments.self_test:
            return _self_test(arguments.csv, arguments.language_labels, logger)
        if not 1 <= arguments.count <= 50:
            parser.error("--count must be between 1 and 50")
        return run_agent(
            arguments.csv,
            arguments.language_labels,
            arguments.export,
            arguments.count,
        )
    except (OSError, ValueError) as error:
        logger.error("application_failed: %s", error)
        print(f"Could not run Playlist Pilot: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
