import io
import json
import logging
from unittest.mock import patch

import pytest

from src.integrations import (
    GeminiClient,
    LLMError,
    SpotifyExportError,
    SpotifyExporter,
    load_dotenv,
    make_llm_client,
    validate_note_preferences,
)


def test_gemini_client_uses_google_generate_content_api_and_json_mode():
    response = {
        "candidates": [
            {"content": {"parts": [{"text": '{"favorite_genre":"pop"}'}]}}
        ]
    }
    client = GeminiClient("test-key", "gemini-test")

    with patch(
        "src.integrations.urllib.request.urlopen",
        return_value=io.BytesIO(json.dumps(response).encode()),
    ) as urlopen:
        preferences = client.parse_notes("I like pop.")

    request = urlopen.call_args.args[0]
    body = json.loads(request.data.decode())
    assert request.full_url.endswith("/models/gemini-test:generateContent")
    assert request.headers["X-goog-api-key"] == "test-key"
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert preferences == {"favorite_genre": "pop"}


def test_llm_note_preferences_are_allowlisted_and_range_checked():
    values = validate_note_preferences(
        {
            "favorite_artist": "Example",
            "target_energy": 1.1,
            "target_tempo_bpm": 120,
            "ignore_safety": True,
        }
    )

    assert values == {"favorite_artist": "Example", "target_tempo_bpm": 120.0}


def test_interactive_agent_requires_google_ai_studio_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(LLMError, match="required"):
        make_llm_client(logging.getLogger("test.gemini"))


def test_dotenv_does_not_override_existing_environment(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_API_KEY=file-value\nNEW_SETTING=value\n", encoding="utf-8")
    monkeypatch.setenv("GEMINI_API_KEY", "existing-value")
    monkeypatch.delenv("NEW_SETTING", raising=False)

    load_dotenv(str(env_file))

    import os

    assert os.environ["GEMINI_API_KEY"] == "existing-value"
    assert os.environ["NEW_SETTING"] == "value"


def test_spotify_export_requires_client_id_and_registered_loopback_uri():
    exporter = SpotifyExporter("")

    with pytest.raises(SpotifyExportError, match="SPOTIFY_CLIENT_ID"):
        exporter._authorize()


def test_spotify_redirect_must_use_explicit_loopback_ip():
    exporter = SpotifyExporter(
        "client-id",
        redirect_uri="http://localhost:8888/callback",
    )

    with pytest.raises(SpotifyExportError, match="loopback redirect URI"):
        exporter._authorize()
