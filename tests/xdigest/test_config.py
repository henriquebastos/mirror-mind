import json
import pytest
from pathlib import Path

from xdigest.config import load_config


@pytest.fixture
def config_file(tmp_path):
    """Create a minimal config file for testing."""
    config = {
        "schedule": {
            "start_hour": 5,
            "interval_hours": 6,
            "timezone": "America/Sao_Paulo",
        },
        "email": {
            "to": "test@example.com",
            "from": "digest@example.com",
        },
        "x_api": {
            "user_id": "12345",
            "username": "testuser",
            "max_results_per_fetch": 100,
        },
        "content": {
            "interests": ["AI/LLMs", "open source"],
            "exclude": ["politics"],
            "languages": ["en", "pt"],
        },
        "priority_accounts": [
            {"username": "importantuser", "name": "Important User", "note": "Always include"},
        ],
        "analysis": {
            "articles": "dense summary",
            "github_repos": "evaluate relevance",
            "videos": "transcribe via yt-dlp",
        },
        "state": {
            "db_path": str(tmp_path / "state.db"),
        },
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    return path, config


def test_load_config_returns_all_fields(config_file):
    path, expected = config_file
    cfg = load_config(path)

    assert cfg.email_to == "test@example.com"
    assert cfg.email_from == "digest@example.com"
    assert cfg.user_id == "12345"
    assert cfg.username == "testuser"
    assert cfg.max_results_per_fetch == 100
    assert cfg.timezone == "America/Sao_Paulo"
    assert cfg.interval_hours == 6
    assert "AI/LLMs" in cfg.interests
    assert "politics" in cfg.exclude
    assert cfg.priority_usernames == {"importantuser"}
    assert str(cfg.db_path).endswith("state.db")


def test_load_config_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_config(Path("/nonexistent/config.json"))


def test_load_config_expands_tilde(tmp_path):
    """db_path with ~ should be expanded."""
    config = {
        "schedule": {"start_hour": 5, "interval_hours": 6, "timezone": "UTC"},
        "email": {"to": "a@b.com", "from": "c@d.com"},
        "x_api": {"user_id": "1", "username": "u", "max_results_per_fetch": 50},
        "content": {"interests": [], "exclude": [], "languages": ["en"]},
        "priority_accounts": [],
        "analysis": {},
        "state": {"db_path": "~/.config/espelho/xdigest/state.db"},
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))

    cfg = load_config(path)
    assert "~" not in str(cfg.db_path)
    assert cfg.db_path.is_absolute()
