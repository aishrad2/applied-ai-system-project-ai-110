# Playlist Pilot Model Card

## Intended use

This classroom music recommender turns a short vibe description into a playlist
from the local Billboard/Spotify catalog. It is not a music-language detector,
and it does not use a model to select or rank tracks.

## How it works

An optional OpenAI-compatible model converts the sentence into a validated
profile. Without a key, a small keyword parser is used. Python derives mood
from 0.5 valence/energy cutoffs and era from the year in `first_week`, which is
the Billboard chart debut date. A weighted scorer compares each track with the
confirmed mood, era, setting, genre tags, and audio-feature hints. A verifier
checks catalog membership, duplicates, genre/era filters, and a playlist
duration within 10% of the target.

## Data source and bias

The dataset is Billboard Hot 100 chart data, mostly US charting hits from 1958
to 2026, enriched with Spotify audio features. It favors popular US charting
music and has thin coverage for many languages and cultures. Language and
culture are inferred from genre tags only, so results are rough. The AI-created
annotation columns are not read or used. All era and mood labels are derived
by project code.

Citation: Muthathohirin, L., and Kaggle Automation Squad. (2026). *Billboard
Hot 100 & Spotify Audio Features: 68-Year Music Telemetry Benchmark*. Kaggle.
https://www.kaggle.com/datasets/luthfimuthathohirin/billboard-hot-100-spotify-audio-features

The Kaggle page lists the dataset license as **CC0: Public Domain**:
https://creativecommons.org/publicdomain/zero/1.0/

## Limitations

The catalog reflects chart popularity, not the breadth of global music.
Audio-feature similarity is an approximation of subjective preferences.
Unsupported genre/language requests receive a low-coverage warning rather than
fabricated matches. The local keyword fallback is intentionally small.

## Evaluation

Unit tests cover allowlisted catalog loading, derived labels, profile schema
validation and fallback, scoring, duration verification, retries, confidence,
and CSV escaping. `python tests/reliability.py` exercises twelve fixed profiles,
including conflicts, prompt-injection-style text, low-coverage Hindi, and a
narrow era.


- latin pop
- changing to prompt instead of quiz