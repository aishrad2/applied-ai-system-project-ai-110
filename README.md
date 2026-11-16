# Playlist Pilot

## Original Project

This builds on my Music Recommender Simulation. The original loaded a small song catalog and a user profile (genre, mood, energy, tempo and a few other tastes), scored every song with a weighted formula, and ranked them with a short reason for each match. It was a teaching demo, and some of the recommender methods were still placeholders (more details in OLD_README.md).

## Title and Summary

Playlist Pilot builds a playlist from a short quiz.

I listen to music from different languages and cultures, and I split my playlists by mood and time period. Spotify makes that hard, and finding songs for a specific mood is even harder. So you answer 4 questions, add optional notes, and the system builds a playlist, checks its own work, and exports it.

## Architecture Overview

The full diagram is in [diagrams/architecture.mmd](diagrams/architecture.mmd). The flow is:

- The four quiz answers and notes are sanitized and turned into a profile
- Gemini interprets the notes; an allowlisted keyword parser is used if Gemini fails
- A validator checks the profile and asks the user which preference wins when inputs conflict
- The agent asks the deterministic scorer to rank songs from the catalog
- A verifier checks catalog membership, labelled language and era, duplicate tracks, and playlist length
- If a check fails, the agent swaps songs and tries again, up to 3 times
- After 3 failed tries it stops and shows the closest playlist and what went wrong
- Gemini writes the playlist name and reasons using only the verified scores; a template is used if explanation generation fails
- I approve the playlist before anything is exported
- Every step is logged, and a separate tester runs fixed profiles through the same pipeline

The normal interactive agent requires a Gemini API key. Gemini interprets notes and explains results, but never chooses or ranks songs: the scorer, verifier, retry loop, and export checks are Python code.

## Setup Instructions

Python 3.10 or newer is required. The interactive AI agent requires a Gemini API key from Google AI Studio. Add it to the ignored local `.env` file:

```
GEMINI_API_KEY=your_google_ai_studio_key
GEMINI_MODEL=gemini-2.5-flash
```

The `.env` file is git-ignored; never commit or share the key. Notes are sent to Gemini when interpreted, and selected song metadata and score reasons are sent when Gemini writes the explanation; do not include sensitive information. Google AI Studio quotas and billing depend on the account and model, so check the current terms before use.

Install dependencies and run the agent from the repository root:

```
python -m venv .venv
```

On Windows:

```
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m src.main
```

On macOS or Linux:

```
source .venv/bin/activate
pip install -r requirements.txt
python -m src.main
```

The app uses `data/spotify_songs.csv` when present, otherwise `data/songs.csv`.
To select a catalog explicitly, pass `--csv path/to/catalog.csv`.

To run the recommender with the downloaded Spotify CSV instead of the small sample catalog:

```
python -m src.main --csv data/spotify_songs.csv
```

Mood is derived from energy and valence, and era is derived from the release date. The Spotify dataset does not include song-language labels. To request language-specific playlists, create `data/language_labels.csv` with `track_id,language` columns and pass `--language-labels data/language_labels.csv`; unknown languages are never presented as verified matches.

To run the tests:

```
python -m pytest
```

The fixed-profile reliability test runs without Gemini or Spotify:

```
python -m src.main --self-test
```

Spotify playlist creation is an optional export destination, but requires a Spotify developer app. Set `SPOTIFY_CLIENT_ID` in `.env`, register the exact loopback URI `http://127.0.0.1:8888/callback` in the Spotify app settings, then run:

```
python -m src.main --export spotify
```

Nothing is exported until you approve the proposed playlist. The approved `playlist.csv` is saved first; if Spotify export fails, it remains available with Spotify search links. Spotify account and API eligibility requirements may apply.

Logs are written to logs/run.log.

## Sample Interactions

Example 1: normal request

Input: language Spanish, mood nostalgic, era 2010s, setting late night drive. Notes: nothing too slow.

Output: [paste real output from your run]

Example 2: notes box

Input: language Hindi, mood chill, era 2000s, setting studying. Notes: no loud songs, mostly acoustic.

Output: [paste real output from your run]

Example 3: conflicting input

Input: language English, mood calm, era any, setting workout. Notes: keep it hype.

Output: [paste real output from your run, should show the clarifying question]

## Design Decisions

Scorer stays deterministic. I wanted every song in a playlist to trace back to a score I can explain, so the LLM does not pick songs.

Local catalog instead of live Spotify recommendations. The system uses the downloaded Spotify metadata/audio-feature catalog (28,356 unique tracks after duplicate removal) and does not rely on Spotify's recommendation endpoint.

Mood and era are derived when the source has no labels. Era comes from the release date. Mood uses four simple energy/valence quadrants.

Language is not inferred. The dataset has no language column; users can supply a manually labelled `track_id,language` CSV. Language-constrained requests are verified, and missing labels are reported rather than guessed.

Spotify export is optional. The default destination is a CSV plus search links; Spotify authorization is requested only after the user approves the playlist.

Stops after 3 tries. I would rather show the closest playlist and say what failed than quietly return something wrong.

Human approval before export. Nothing is exported until I say yes.

Trade-offs:

- The catalog is small, so some language and mood combinations have few songs
- Hand labeling takes time and can be wrong
- Four mood quadrants are simple and miss a lot of nuance
- The keyword fallback is less flexible than the LLM parser

## Testing Summary

The test suite has 26 passing tests covering scoring, Spotify CSV normalization, Gemini request formatting and key requirements, input conflicts, retries, language verification, deterministic runs, approval-gated export, and CSV formula-injection protection.

The fixed-profile reliability run (`python -m src.main --self-test --csv data/spotify_songs.csv`) produced:

| Measure | Result |
|---|---:|
| Profiles run | 4 |
| Verifier pass rate | 4/4 |
| Repeatability | 4/4 |

Language-specific playlists cannot be verified against the downloaded catalog until language labels are provided. Gemini and Spotify network calls are isolated behind integrations and were not exercised with live credentials in the automated tests.

