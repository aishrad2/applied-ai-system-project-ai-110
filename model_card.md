# Playlist Pilot Model Card

## Intended use

Playlist Pilot is a human-in-the-loop music recommendation agent. It turns a
short vibe description into a playlist from a fixed Billboard/Spotify catalog.
It does not analyze lyrics or detect language.

## How it works

This is more than natural-language processing: the app interprets a request,
asks follow-up questions when needed, shows the profile for approval, builds
and verifies a playlist, and offers an approved export. Gemini handles the
language step; Python runs the recommendation workflow and chooses the songs.

In my setup, the API is Gemini. Gemini creates a structured
profile but does not rank or select tracks. If it is unavailable or returns
an invalid profile, a local keyword parser is used. Python derives mood and
era, scores songs using the confirmed profile and catalog features, then
checks genre/era filters, duplicates, catalog membership, and playlist length.

## Data source and bias

The dataset is Billboard Hot 100 chart data, mostly US charting hits from 1958
to 2026, enriched with Spotify audio features. It favors popular US charting
music and has thin coverage for many languages and cultures. Language and
culture are inferred from genre tags only, so results are rough. The AI-created
annotation columns are not read or used. All era and mood labels are derived
by project code.

After testing, I changed multiple intial (not billboard 100s) datasets to match the fields the recommender
already used—genre tags, audio features, chart dates, and Spotify metadata.
Its range of years and genres works better for varied playlists. It still
mostly represents US chart hits, not global music.

Citation: Muthathohirin, L., and Kaggle Automation Squad. (2026). *Billboard
Hot 100 & Spotify Audio Features: 68-Year Music Telemetry Benchmark*. Kaggle.
https://www.kaggle.com/datasets/luthfimuthathohirin/billboard-hot-100-spotify-audio-features

The Kaggle page lists the dataset license as **CC0: Public Domain**:
https://creativecommons.org/publicdomain/zero/1.0/

## Limitations and bias

The catalog reflects chart popularity, not the breadth of global music.
It is mostly US chart hits and has thin coverage for many languages and
cultures, so recommendations can overrepresent already popular artists and
underrepresent less-charted music. The app does not analyze lyrics or detect
language; cultural and language requests rely on genre tags. Mood labels come
from fixed energy and valence thresholds, and audio-feature similarity is only
an approximation of subjective preferences. Unsupported genre/language
requests receive a low-coverage warning rather than fabricated matches. The
local keyword fallback is intentionally small. This is an attempt to reduce hallucination.

## Misuse and safeguards

This kind of system could be misused to profile listeners or steer their
choices. Playlist Pilot uses no listening history. Its prompt tells Gemini to
treat the request as data, and Python validates the returned profile and
chooses from the fixed catalog. These steps reduce prompt-injection risk but
cannot guarantee prevention; the injection-style reliability test exercises
the local fallback, not Gemini. Requests and credentials are not logged.
Spotify export requires user approval and creates a private playlist.

## Evaluation

Unit tests cover allowlisted catalog loading, derived labels, profile schema
validation and fallback, scoring, duration verification, retries, confidence,
and CSV download. `python tests/reliability.py` exercises twelve fixed profiles,
including conflicts, prompt-injection-style text, low-coverage Hindi, and a
narrow era.

## Reflection

### Reliability surprise

I was surprised that “Latin pop” became two tags, `latin` and `pop`, so regular
pop songs passed the genre filter despite high confidence. I fixed this by
preferring the exact, longer catalog tag and added a regression test. It also
showed that a high score does not necessarily mean the playlist understood
what the user meant.

### Collaboration with AI

I used Claude to brainstorm the initial idea, Gemini as the app's API, and
Copilot for later development; I preferred working with Copilot on the code.
I accepted its suggestion to treat `latin pop` as one tag and add a test. I
didn't accept its first suggestion to reword the request: the parser should
handle a normal phrase, so I fixed the parser instead. I also has a midway pivot to a free-text
prompt from a quiz, keeping brief follow-ups for unclear preferences.