from src.playlist import build_playlist, score_song, verify
from src.profile import DEFAULTS, build_profile


def _profile(**overrides):
    values = {key: {"value": value, "source": "stated", "confidence": .9}
              for key, value in DEFAULTS.items()}
    values.update(overrides)
    values["_meta"] = {"unmatched_terms": []}
    return values


def _song(track_id, title, era="2000s", tags=None, duration=180000):
    return {
        "track_id": track_id, "spotify_uri": f"spotify:track:{track_id}",
        "title": title, "artist": "Artist", "genre_tags": tags or ["pop"],
        "era": era, "mood": "happy/hype", "duration_ms": duration,
        "energy": .8, "tempo": 120., "valence": .8, "danceability": .8,
        "acousticness": .2, "speechiness": .05, "instrumentalness": .1,
        "liveness": .1, "loudness": -8.,
    }


def test_duration_selection_and_feature_breakdown():
    songs = [_song("a", "One"), _song("b", "Two"), _song("c", "Three")]
    profile = _profile(length_minutes={"value": 6, "source": "stated", "confidence": .9})
    result = build_playlist(songs, profile)

    assert not result["issues"]
    assert len(result["tracks"]) == 2
    assert "energy" in result["tracks"][0]["breakdown"]
    assert 0 <= result["confidence"] <= 1


def test_tags_and_era_are_enforced_by_selection_and_verifier():
    songs = [_song("a", "Pop"), _song("b", "Rap", tags=["rap"])]
    profile = _profile(
        era={"value": "2000s", "source": "stated", "confidence": 1},
        genre_tags={"value": ["pop"], "source": "stated", "confidence": 1},
        length_minutes={"value": 3, "source": "stated", "confidence": 1},
    )
    result = build_playlist(songs, profile)
    assert not result["issues"]
    assert all(song["genre_tags"] == ["pop"] for song in result["tracks"])

    wrong = verify([_song("b", "wrong", era="2010s", tags=["rap"])], songs, profile)
    assert any("filters" in issue for issue in wrong)


def test_latin_pop_request_excludes_generic_pop_tracks():
    songs = [
        _song("generic-pop", "Generic Pop", tags=["pop"]),
        _song("latin-pop", "Latin Pop", tags=["latin pop"]),
    ]
    profile = build_profile(
        "Latin pop",
        ["latin", "pop", "latin pop"],
        allow_llm=False,
    )
    profile["length_minutes"] = {
        "value": 3, "source": "stated", "confidence": 1
    }

    result = build_playlist(songs, profile)

    assert [song["track_id"] for song in result["tracks"]] == ["latin-pop"]
    assert not result["issues"]


def test_retry_cap_and_confidence_bounds_for_impossible_era():
    songs = [_song("a", "Only song")]
    profile = _profile(
        era={"value": "1980s", "source": "stated", "confidence": 1},
        length_minutes={"value": 3, "source": "stated", "confidence": 1},
    )
    result = build_playlist(songs, profile)
    assert result["attempts"] == 3
    assert result["issues"]
    assert result["tracks"]
    assert 0 <= result["confidence"] <= 1
