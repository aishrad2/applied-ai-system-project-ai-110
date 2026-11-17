import json

import pytest

from src.profile import (
    DEFAULTS,
    _validate,
    build_profile,
    fill_defaults,
    parse_confidence,
    sanitize,
)


def test_sanitizer_removes_controls_newlines_and_caps_input():
    cleaned = sanitize("Rainy\r\nday\x00" + "x" * 250)
    assert "\n" not in cleaned and "\r" not in cleaned
    assert "\x00" not in cleaned
    assert len(cleaned) == 200


def test_keyword_fallback_maps_vibe_and_spanish_to_catalog_tags(caplog):
    with caplog.at_level("INFO", logger="src.profile"):
        profile = build_profile(
            "rainy day studying, sad but not slow, early 2000s R&B",
            ["r&b", "pop"],
            allow_llm=False,
        )
    assert profile["mood"]["value"] == "sad/mellow"
    assert profile["era"]["value"] == "2000s"
    assert profile["setting"]["value"] == "studying"
    assert profile["genre_tags"]["value"] == ["r&b"]
    assert profile["tempo_hint"]["value"] == 120
    assert profile["length_minutes"]["value"] == 30

    with caplog.at_level("INFO", logger="src.profile"):
        spanish = build_profile("Spanish songs", ["latin", "reggaeton"], allow_llm=False)
    assert spanish["genre_tags"]["value"] == ["latin", "reggaeton"]
    assert "profile_keyword_fallback" in caplog.text


def test_compound_catalog_genre_is_not_split_in_keyword_fallback():
    profile = build_profile(
        "Latin pop party",
        ["latin", "pop", "latin pop"],
        allow_llm=False,
    )
    assert profile["genre_tags"]["value"] == ["latin pop"]


def test_unavailable_hindi_tag_is_reported_without_invention():
    profile = build_profile("Hindi songs", ["pop", "latin"], allow_llm=False)
    assert profile["genre_tags"]["value"] == []
    assert profile["_meta"]["unmatched_terms"] == ["hindi"]
    assert parse_confidence(profile) < .6


def test_schema_rejects_genres_outside_catalog():
    raw = {
        key: {"value": value, "source": "default", "confidence": .5}
        for key, value in DEFAULTS.items()
    }
    raw["genre_tags"]["value"] = ["bollywood"]
    with pytest.raises(ValueError, match="catalog tags"):
        _validate(raw, ["pop", "latin"])


def test_invalid_llm_profile_uses_keyword_fallback(monkeypatch, caplog):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("src.profile._llm_profile", lambda text, tags: {"bad": "schema"})
    with caplog.at_level("WARNING", logger="src.profile"):
        profile = build_profile("Spanish songs", ["latin", "reggaeton"])
    assert profile["_meta"]["used_fallback"]
    assert profile["genre_tags"]["value"] == ["latin", "reggaeton"]
    assert "profile_llm_fallback" in caplog.text


def test_followup_cap_defaults_low_confidence_fields_and_records_assumptions():
    profile = build_profile("music", ["pop"], allow_llm=False)
    profile["mood"]["confidence"] = .2
    profile["era"]["confidence"] = .2
    fill_defaults(profile)
    assert profile["mood"]["value"] == DEFAULTS["mood"]
    assert profile["mood"]["source"] == "default"
    assert len(profile["_meta"]["assumptions"]) == 3


def test_openai_compatible_request_is_json_and_temperature_zero(monkeypatch):
    raw = {
        key: {"value": value, "source": "default", "confidence": .8}
        for key, value in DEFAULTS.items()
    }
    raw["mood"] = {"value": "sad/mellow", "source": "stated", "confidence": .9}

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
        def read(self):
            return json.dumps({
                "choices": [{"message": {"content": json.dumps(raw)}}]
            }).encode()

    seen = {}
    def fake_open(request, timeout):
        seen["request"] = request
        seen["timeout"] = timeout
        return Response()

    monkeypatch.setenv("OPENAI_API_KEY", "local-test-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setattr("urllib.request.urlopen", fake_open)

    profile = build_profile("sad music", ["pop"])
    payload = json.loads(seen["request"].data)
    assert seen["request"].full_url.endswith("/chat/completions")
    assert payload["temperature"] == 0
    assert payload["model"] == "test-model"
    assert profile["mood"]["value"] == "sad/mellow"
    assert profile["_meta"]["schema_valid"]


def test_explicit_compound_genre_overrides_split_llm_tags(monkeypatch):
    raw = {
        key: {"value": value, "source": "default", "confidence": .8}
        for key, value in DEFAULTS.items()
    }
    raw["genre_tags"] = {
        "value": ["latin", "pop"], "source": "inferred", "confidence": .75
    }
    monkeypatch.setenv("OPENAI_API_KEY", "local-test-key")
    monkeypatch.setattr("src.profile._llm_profile", lambda text, tags: raw)

    profile = build_profile("Latin pop", ["latin", "pop", "latin pop"])

    assert profile["genre_tags"]["value"] == ["latin pop"]
