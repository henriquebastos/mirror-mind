"""Configuration loader for xdigest."""

import json
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_CONFIG_PATH = Path("~/.config/espelho/xdigest/config.json").expanduser()


@dataclass(frozen=True)
class Config:
    """Immutable xdigest configuration."""

    # Email
    email_to: str
    email_from: str

    # X API
    user_id: str
    username: str
    max_results_per_fetch: int

    # Schedule
    timezone: str
    start_hour: int
    interval_hours: int

    # Content filtering
    interests: list[str]
    exclude: list[str]
    languages: list[str]
    priority_usernames: set[str]

    # Analysis prompts
    analysis: dict

    # State
    db_path: Path

    # Priority accounts (full records)
    priority_accounts: list[dict] = field(default_factory=list)


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    """Load config from JSON file. Raises FileNotFoundError if missing."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    raw = json.loads(path.read_text())

    db_path = Path(raw.get("state", {}).get("db_path", "~/.config/espelho/xdigest/state.db"))
    if str(db_path).startswith("~"):
        db_path = db_path.expanduser()

    return Config(
        email_to=raw["email"]["to"],
        email_from=raw["email"]["from"],
        user_id=raw["x_api"]["user_id"],
        username=raw["x_api"]["username"],
        max_results_per_fetch=raw["x_api"].get("max_results_per_fetch", 100),
        timezone=raw["schedule"].get("timezone", "America/Sao_Paulo"),
        start_hour=raw["schedule"].get("start_hour", 5),
        interval_hours=raw["schedule"].get("interval_hours", 6),
        interests=raw.get("content", {}).get("interests", []),
        exclude=raw.get("content", {}).get("exclude", []),
        languages=raw.get("content", {}).get("languages", ["en"]),
        priority_usernames={
            a["username"] for a in raw.get("priority_accounts", [])
        },
        analysis=raw.get("analysis", {}),
        db_path=db_path,
        priority_accounts=raw.get("priority_accounts", []),
    )
