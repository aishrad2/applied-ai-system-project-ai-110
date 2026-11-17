# Playlist Pilot

A small Streamlit playlist builder. Describe one vibe in a sentence; the app
parses a profile, asks up to two fixed follow-up questions if mood, era, or
setting is unclear, shows the profile for confirmation, then scores and verifies
tracks before offering a CSV download.

The app runs without an API key. An optional OpenAI-compatible chat-completions
endpoint interprets the sentence; Python validates the response and chooses all
tracks. The language model never ranks songs.

## Run

Python 3.10+ is supported. From the repository root on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m streamlit run src\main.py
```

Optional `.env` settings are shown in `.env.example`. `OPENAI_BASE_URL`,
`OPENAI_MODEL`, and `OPENAI_API_KEY` configure any compatible API. Without a
key, a small local keyword parser is used. Network requests have a timeout;
invalid responses also use the local parser.

After confirming the profile and playlist, approve the export to save
`playlist.csv` in the repository root. Spotify export is optional: configure
`SPOTIFY_CLIENT_ID`, register
`http://127.0.0.1:8888/callback`, and choose the private Spotify export option.
Only the `playlist-modify-private` scope is requested. CSV export remains
available if Spotify authorization or API calls fail.

## Data source

The catalog is Billboard Hot 100 chart data, mostly popular US charting music
from 1958 to 2026, enriched with Spotify audio features. `first_week` is the
chart debut date, not the song's release date. Only the source-column allowlist
in `src/catalog.py` is read. AI-generated annotation columns are not used;
genre tags come from `spotify_genre`, while era and mood are derived by code.

The catalog is biased toward US chart hits and has thin coverage for many
languages and cultures. Language and culture requests are interpreted from
genre tags only, so those matches are rough. Unsupported requests are not
invented; the app flags low coverage and asks for clarification.

Citation: Muthathohirin, L., and Kaggle Automation Squad. (2026). *Billboard
Hot 100 & Spotify Audio Features: 68-Year Music Telemetry Benchmark*. Kaggle.
https://www.kaggle.com/datasets/luthfimuthathohirin/billboard-hot-100-spotify-audio-features

The Kaggle dataset page lists the license as **CC0: Public Domain**:
https://creativecommons.org/publicdomain/zero/1.0/

## Checks

```powershell
python -m pytest -q
python tests\reliability.py
```

Runtime logs are written to `logs/run.log`; credentials and request text are
not logged.
