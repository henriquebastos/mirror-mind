"""Tests for xdigest.cli — checkpoint pipeline orchestration."""

import json
import pytest
from pathlib import Path

from xdigest.cli import Pipeline
from xdigest.config import Config


@pytest.fixture
def config(tmp_path):
    return Config(
        email_to="test@test.com",
        email_from="digest@test.com",
        user_id="12345",
        username="testuser",
        max_results_per_fetch=100,
        timezone="America/Sao_Paulo",
        start_hour=5,
        interval_hours=6,
        interests=["AI/LLMs"],
        exclude=["politics"],
        languages=["en"],
        priority_usernames={"badlogic"},
        analysis={"articles": "dense summary"},
        db_path=tmp_path / "state.db",
        priority_accounts=[{"username": "badlogic", "name": "Mario", "note": "Pi creator"}],
    )


@pytest.fixture
def run_dir(tmp_path):
    d = tmp_path / "runs" / "2026-04-13T10-00-00"
    d.mkdir(parents=True)
    return d


def test_pipeline_creates_run_directory(config, tmp_path):
    p = Pipeline(config=config, base_dir=tmp_path / "runs")
    assert p.run_dir.exists()
    assert p.run_dir.is_dir()


def test_pipeline_step_writes_checkpoint(config, run_dir):
    p = Pipeline(config=config, base_dir=run_dir.parent, run_id=run_dir.name)

    # Simulate writing a checkpoint
    p.save_checkpoint("1_fetch", {"tweets": [{"id": "1", "text": "hello"}]})

    checkpoint = run_dir / "1_fetch.json"
    assert checkpoint.exists()
    data = json.loads(checkpoint.read_text())
    assert data["tweets"][0]["id"] == "1"


def test_pipeline_skips_completed_steps(config, run_dir):
    p = Pipeline(config=config, base_dir=run_dir.parent, run_id=run_dir.name)

    # Pre-create a checkpoint
    (run_dir / "1_fetch.json").write_text(json.dumps({"tweets": []}))

    assert p.is_step_complete("1_fetch")
    assert not p.is_step_complete("2_triage")


def test_pipeline_loads_checkpoint(config, run_dir):
    p = Pipeline(config=config, base_dir=run_dir.parent, run_id=run_dir.name)

    data = {"tweets": [{"id": "42", "text": "saved"}]}
    (run_dir / "1_fetch.json").write_text(json.dumps(data))

    loaded = p.load_checkpoint("1_fetch")
    assert loaded["tweets"][0]["id"] == "42"


def test_pipeline_full_run_with_injected_deps(config, tmp_path):
    """End-to-end pipeline with all dependencies mocked."""
    fetch_data = {
        "tweets": [
            {"id": "1", "text": "AI agents rock", "author_username": "alice",
             "author_name": "Alice", "author_id": "100", "created_at": "2026-04-13T12:00:00.000Z",
             "public_metrics": {"like_count": 5}, "entities": {}, "urls": [],
             "tweet_type": "original", "referenced_tweets": None},
        ]
    }
    triage_response = json.dumps({
        "relevant": [{"id": "1", "reason": "AI topic", "section": "Agents"}],
        "excluded": [],
    })
    analysis_response = json.dumps({
        "summary": "Interesting take on AI agents.",
        "key_points": ["Agents are cool"],
        "section": "Agents",
    })

    analysis_response = json.dumps(
        {"summary": "Interesting take on AI agents.",
         "key_points": ["Agents are cool"], "section": "Agents"},
    )

    pi_calls = []
    def fake_pi(prompt, **kwargs):
        pi_calls.append(prompt)
        if "Classify each tweet" in prompt or "relevance filter" in prompt:
            return triage_response
        return analysis_response

    send_calls = []
    def fake_send(cmd, **kwargs):
        send_calls.append(cmd)
        return json.dumps({"id": "msg1", "threadId": "t1"})

    def fake_xurl(cmd, **kwargs):
        return json.dumps({
            "data": [
                {"id": "1", "text": "AI agents rock", "author_id": "100",
                 "created_at": "2026-04-13T12:00:00.000Z",
                 "public_metrics": {"like_count": 5}, "entities": {}},
            ],
            "includes": {"users": [{"id": "100", "username": "alice", "name": "Alice"}]},
            "meta": {"result_count": 1},
        })

    def fake_curl(url):
        return "<html><body><p>Article content</p></body></html>"

    p = Pipeline(
        config=config,
        base_dir=tmp_path / "runs",
        deps={
            "run_command": fake_xurl,
            "run_pi": fake_pi,
            "run_send": fake_send,
            "fetch_article": fake_curl,
            "fetch_captions": lambda url: "",
        },
    )

    p.run()

    # All checkpoints should exist
    assert p.is_step_complete("1_fetch")
    assert p.is_step_complete("2_triage")
    assert p.is_step_complete("3_analyze")
    assert p.is_step_complete("4_render")
    assert p.is_step_complete("5_sent")

    # Verify email was sent
    assert len(send_calls) == 1
