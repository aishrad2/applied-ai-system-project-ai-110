import csv
from pathlib import Path

from src.main import run_agent


class FakeGemini:
    def parse_notes(self, notes):
        return {"target_energy": 0.8} if notes else {}

    def explain(self, result):
        return {
            "playlist_name": "Gemini Playlist",
            "reasons": [
                f"Recommended from score {score:.1f}"
                for _, score, _ in result.recommendations
            ],
        }


def test_approved_interactive_run_creates_csv_after_gemini_calls(
    tmp_path, monkeypatch
):
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("src.main.make_llm_client", lambda logger: FakeGemini())
    answers = iter(["happy", "any", "any", "commute", "I like pop", "yes"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))

    result = run_agent(str(repo_root / "data" / "songs.csv"), count=2)

    assert result == 0
    with (tmp_path / "playlist.csv").open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 2
    assert (tmp_path / "logs" / "run.log").is_file()


def test_declined_playlist_is_not_exported(tmp_path, monkeypatch):
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("src.main.make_llm_client", lambda logger: FakeGemini())
    answers = iter(["happy", "any", "any", "commute", "", "no"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))

    result = run_agent(str(repo_root / "data" / "songs.csv"), count=2)

    assert result == 0
    assert not (tmp_path / "playlist.csv").exists()


def test_normal_agent_run_requires_gemini_key(tmp_path, monkeypatch, capsys):
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=\n", encoding="utf-8")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def reject_input(prompt):
        raise AssertionError("quiz should not start without a Gemini key")

    monkeypatch.setattr("builtins.input", reject_input)

    result = run_agent(str(repo_root / "data" / "songs.csv"))

    assert result == 1
    assert "GEMINI_API_KEY is required" in capsys.readouterr().out
