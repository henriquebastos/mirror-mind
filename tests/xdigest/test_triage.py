"""Tests for xdigest.triage — LLM-based tweet filtering via pi CLI."""

import json
import pytest

from xdigest.fetch import Tweet
from xdigest.triage import triage_tweets, build_triage_prompt, parse_triage_response


def make_tweet(id, text, username="alice", **kwargs):
    return Tweet(
        id=id, text=text, author_id="100", author_username=username,
        author_name=username.title(), created_at="2026-04-13T12:00:00.000Z",
        public_metrics={"like_count": 5}, entities={},
        referenced_tweets=None, urls=kwargs.get("urls", []),
        tweet_type=kwargs.get("tweet_type", "original"),
    )


def test_build_triage_prompt_includes_tweets():
    tweets = [
        make_tweet("1", "AI agents are the future"),
        make_tweet("2", "Buy my course now!"),
    ]
    prompt = build_triage_prompt(
        tweets,
        interests=["AI/LLMs", "agents"],
        exclude=["course promotion"],
        priority_usernames=set(),
    )
    assert "AI agents are the future" in prompt
    assert "Buy my course now!" in prompt
    assert "AI/LLMs" in prompt


def test_build_triage_prompt_marks_priority():
    tweets = [make_tweet("1", "Pi update", username="badlogic")]
    prompt = build_triage_prompt(
        tweets,
        interests=["AI"],
        exclude=[],
        priority_usernames={"badlogic"},
    )
    assert "PRIORITY" in prompt


def test_parse_triage_response_extracts_ids():
    response = json.dumps({
        "relevant": [
            {"id": "1", "reason": "AI agent discussion", "section": "Agents"},
            {"id": "3", "reason": "Open source tool", "section": "Tools"},
        ],
        "excluded": [
            {"id": "2", "reason": "Course promotion"},
        ],
    })
    relevant, excluded = parse_triage_response(response)
    assert {r["id"] for r in relevant} == {"1", "3"}
    assert {e["id"] for e in excluded} == {"2"}


def test_triage_tweets_returns_filtered_list():
    tweets = [
        make_tweet("1", "New Pi extension for MCP"),
        make_tweet("2", "10 things I learned thread"),
        make_tweet("3", "Cloudflare Workers update"),
    ]

    # Fake pi runner that returns a canned triage
    def fake_pi(prompt, **kwargs):
        return json.dumps({
            "relevant": [
                {"id": "1", "reason": "Pi ecosystem", "section": "Pi"},
                {"id": "3", "reason": "Infra for agents", "section": "Infra"},
            ],
            "excluded": [
                {"id": "2", "reason": "Generic listicle"},
            ],
        })

    relevant, triage_data = triage_tweets(
        tweets,
        interests=["AI/LLMs", "Pi"],
        exclude=["generic threads"],
        priority_usernames=set(),
        run_pi=fake_pi,
    )

    assert len(relevant) == 2
    assert {t.id for t in relevant} == {"1", "3"}
    assert len(triage_data["relevant"]) == 2


def test_triage_preserves_priority_even_if_not_in_llm_response():
    """Priority accounts should always be included even if LLM excludes them."""
    tweets = [
        make_tweet("1", "Some Pi thing", username="badlogic"),
        make_tweet("2", "Random tweet", username="nobody"),
    ]

    def fake_pi(prompt, **kwargs):
        # LLM only returns tweet 2
        return json.dumps({
            "relevant": [{"id": "2", "reason": "Interesting", "section": "General"}],
            "excluded": [{"id": "1", "reason": "Not relevant"}],
        })

    relevant, _ = triage_tweets(
        tweets,
        interests=["AI"],
        exclude=[],
        priority_usernames={"badlogic"},
        run_pi=fake_pi,
    )

    # badlogic should always be included
    assert any(t.id == "1" for t in relevant)
