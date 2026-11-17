import logging
from pathlib import Path

import streamlit as st

from src.catalog import genre_vocabulary, load_catalog
from src.export import csv_bytes, export_spotify
from src.playlist import build_playlist
from src.profile import (
    FOLLOWUP_CHOICES,
    build_profile,
    fill_defaults,
    parse_confidence,
    resolve_followup,
    sanitize,
)


@st.cache_data(show_spinner=False)
def _catalog():
    return load_catalog("data/billboard_hot_100_spotify_audio_features_enriched.csv")


def _logger():
    Path("logs").mkdir(exist_ok=True)
    logger = logging.getLogger("playlist_pilot")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler("logs/run.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


def _profile_rows(profile):
    return [
        {
            "Preference": key.replace("_", " ").title(),
            "Value": str(item["value"]),
            "Source": item["source"],
            "Confidence": round(item["confidence"], 2),
        }
        for key, item in profile.items()
        if not key.startswith("_")
    ]


def main():
    st.set_page_config(page_title="Playlist Pilot", page_icon="🎧", layout="wide")
    st.title("Playlist Pilot")
    st.caption("Describe one playlist vibe. The catalog loads only after you submit.")
    logger = _logger()

    with st.form("vibe_form"):
        sentence = st.text_area(
            "What should this playlist feel like?",
            max_chars=200,
            placeholder="Rainy-day studying, sad but not slow, early 2000s R&B",
        )
        submitted = st.form_submit_button("Build my profile", type="primary")
    if submitted:
        sentence = sanitize(sentence)
        if not sentence:
            st.error("Enter a short description first.")
        else:
            try:
                with st.spinner("Loading the Billboard catalog and reading your request..."):
                    songs = _catalog()
                    profile = build_profile(sentence, genre_vocabulary(songs), logger)
            except (OSError, ValueError, RuntimeError) as error:
                logger.error("profile_setup_failed error_type=%s", type(error).__name__)
                st.error(f"Could not prepare the request: {error}")
            else:
                st.session_state["profile"] = profile
                st.session_state["followups"] = 0
                st.session_state["asked"] = []
                st.session_state.pop("playlist", None)
                st.session_state.pop("approved", None)
                st.session_state.pop("spotify_url", None)

    profile = st.session_state.get("profile")
    if not profile:
        return

    uncertain = [
        key for key in ("mood", "era", "setting")
        if profile[key]["confidence"] < .6 and key not in st.session_state["asked"]
    ]
    if uncertain and st.session_state["followups"] < 2:
        key = min(uncertain, key=lambda item: profile[item]["confidence"])
        questions = {
            "mood": "Which mood is closest?",
            "era": "Which chart-debut era do you mean?",
            "setting": "Where will you listen?",
        }
        with st.form("followup_form"):
            answer = st.selectbox(questions[key], FOLLOWUP_CHOICES[key])
            answered = st.form_submit_button("Use this answer")
        if answered:
            resolve_followup(profile, key, answer)
            st.session_state["asked"].append(key)
            st.session_state["followups"] += 1
            st.session_state["profile"] = profile
            st.rerun()
        return
    elif any(profile[key]["confidence"] < .6 for key in ("mood", "era", "setting")):
        st.session_state["profile"] = fill_defaults(profile)
        profile = st.session_state["profile"]

    st.subheader("Confirm your profile")
    st.dataframe(_profile_rows(profile), hide_index=True, use_container_width=True)
    for assumption in profile.get("_meta", {}).get("assumptions", []):
        st.info("Assumption: " + assumption)
    st.caption(f"Parse confidence: {parse_confidence(profile):.2f}")

    st.checkbox("Also create a private Spotify playlist", key="also_spotify")
    if st.button("Confirm profile and build playlist", type="primary"):
        try:
            with st.spinner("Scoring, verifying, and adjusting playlist length..."):
                result = build_playlist(_catalog(), profile, logger)
            st.session_state["playlist"] = result
            st.session_state["approved"] = False
            st.session_state.pop("spotify_url", None)
            st.session_state["csv_data"] = csv_bytes(result["tracks"])
        except (OSError, ValueError, RuntimeError) as error:
            logger.error("playlist_build_failed error_type=%s", type(error).__name__)
            st.error(f"Could not build the playlist: {error}")

    result = st.session_state.get("playlist")
    if not result:
        return
    st.subheader("Playlist")
    st.metric("Playlist confidence", f"{result['confidence']:.2f}", result["label"])
    st.metric(
        "Duration",
        f"{sum(song['duration_ms'] for song in result['tracks']) / 60000:.1f} min",
        f"target {profile['length_minutes']['value']} min",
    )
    st.caption(f"Verified after {result['attempts']} attempt(s).")
    for issue in result["issues"]:
        st.warning(issue)
    st.dataframe(
        [
            {
                "Song": song["title"], "Performer": song["artist"],
                "Score": song["score"], "Reason": song["breakdown"],
            }
            for song in result["tracks"]
        ],
        hide_index=True,
        use_container_width=True,
    )
    if st.button("Approve and export", disabled=st.session_state.get("approved", False)):
        try:
            data = csv_bytes(result["tracks"])
            Path("playlist.csv").write_bytes(data)
            st.session_state["csv_data"] = data
            st.session_state["approved"] = True
        except OSError as error:
            logger.error("csv_export_failed error_type=%s", type(error).__name__)
            st.error(f"Could not save playlist.csv: {error}")
        if st.session_state.get("approved") and st.session_state.get("also_spotify"):
            try:
                with st.spinner("Creating your private Spotify playlist..."):
                    st.session_state["spotify_url"] = export_spotify(
                        result["tracks"], "Playlist Pilot"
                    )
            except RuntimeError as error:
                logger.error("spotify_export_failed error_type=%s", type(error).__name__)
                st.error(f"Spotify export failed; the CSV is still available: {error}")
    if st.session_state.get("approved"):
        st.download_button(
            "Download playlist.csv",
            st.session_state["csv_data"],
            file_name="playlist.csv",
            mime="text/csv",
        )
        if st.session_state.get("spotify_url"):
            st.link_button("Open Spotify playlist", st.session_state["spotify_url"])


if __name__ == "__main__":
    main()
