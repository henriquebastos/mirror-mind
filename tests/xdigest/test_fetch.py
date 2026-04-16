"""Tests for xdigest.fetch — timeline fetching via xurl."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from xdigest.fetch import fetch_timeline, Tweet, enrich_tweets


# Minimal xurl response structure
def make_xurl_response(tweets, users=None, next_token=None):
    """Build a fake xurl JSON response."""
    data = []
    for t in tweets:
        data.append({
            "id": t["id"],
            "text": t["text"],
            "author_id": t.get("author_id", "100"),
            "created_at": t.get("created_at", "2026-04-13T12:00:00.000Z"),
            "public_metrics": t.get("public_metrics", {
                "like_count": 5, "retweet_count": 1, "reply_count": 0, "quote_count": 0,
            }),
            "entities": t.get("entities", {}),
            "referenced_tweets": t.get("referenced_tweets"),
        })
    includes = {}
    if users:
        includes["users"] = users
    result = {"data": data, "includes": includes}
    if next_token:
        result["meta"] = {"next_token": next_token}
    else:
        result["meta"] = {"result_count": len(data)}
    return json.dumps(result)


def fake_run_xurl(responses):
    """Return a callable that yields responses in order."""
    call_count = [0]

    def _run(cmd, **kwargs):
        idx = call_count[0]
        call_count[0] += 1
        if idx < len(responses):
            return responses[idx]
        return json.dumps({"data": [], "meta": {"result_count": 0}})

    return _run


def test_fetch_single_page():
    tweets_data = [
        {"id": "1", "text": "Hello world", "author_id": "100"},
        {"id": "2", "text": "Another tweet", "author_id": "101"},
    ]
    users = [
        {"id": "100", "username": "alice", "name": "Alice"},
        {"id": "101", "username": "bob", "name": "Bob"},
    ]
    response = make_xurl_response(tweets_data, users=users)
    runner = fake_run_xurl([response])

    tweets = fetch_timeline(
        user_id="14227855",
        max_results=100,
        run_command=runner,
    )

    assert len(tweets) == 2
    assert tweets[0].id == "1"
    assert tweets[0].text == "Hello world"
    assert tweets[0].author_username == "alice"


def test_fetch_paginates():
    page1_tweets = [{"id": str(i), "text": f"Tweet {i}", "author_id": "100"} for i in range(100)]
    page2_tweets = [{"id": str(i), "text": f"Tweet {i}", "author_id": "100"} for i in range(100, 150)]
    users = [{"id": "100", "username": "alice", "name": "Alice"}]

    page1 = make_xurl_response(page1_tweets, users=users, next_token="TOKEN_PAGE2")
    page2 = make_xurl_response(page2_tweets, users=users)
    runner = fake_run_xurl([page1, page2])

    tweets = fetch_timeline(
        user_id="14227855",
        max_results=100,
        run_command=runner,
    )

    assert len(tweets) == 150


def test_fetch_empty_timeline():
    response = json.dumps({"data": [], "meta": {"result_count": 0}})
    runner = fake_run_xurl([response])

    tweets = fetch_timeline(user_id="14227855", max_results=100, run_command=runner)
    assert tweets == []


def test_enrich_tweets_extracts_urls():
    tweets = [
        Tweet(
            id="1",
            text="Check this out https://t.co/abc",
            author_id="100",
            author_username="alice",
            author_name="Alice",
            created_at="2026-04-13T12:00:00.000Z",
            public_metrics={"like_count": 10},
            entities={
                "urls": [
                    {
                        "expanded_url": "https://example.com/article",
                        "display_url": "example.com/article",
                    }
                ]
            },
            referenced_tweets=None,
        ),
    ]

    enriched = enrich_tweets(tweets)
    assert enriched[0].urls == ["https://example.com/article"]


def test_enrich_tweets_detects_type():
    """Retweets, quotes, and replies should be tagged."""
    rt = Tweet(
        id="1", text="RT text", author_id="100", author_username="alice",
        author_name="Alice", created_at="2026-04-13T12:00:00.000Z",
        public_metrics={}, entities={},
        referenced_tweets=[{"type": "retweeted", "id": "orig1"}],
    )
    quote = Tweet(
        id="2", text="My take:", author_id="100", author_username="alice",
        author_name="Alice", created_at="2026-04-13T12:00:00.000Z",
        public_metrics={}, entities={},
        referenced_tweets=[{"type": "quoted", "id": "orig2"}],
    )
    original = Tweet(
        id="3", text="Original thought", author_id="100", author_username="alice",
        author_name="Alice", created_at="2026-04-13T12:00:00.000Z",
        public_metrics={}, entities={},
        referenced_tweets=None,
    )

    enriched = enrich_tweets([rt, quote, original])
    assert enriched[0].tweet_type == "retweet"
    assert enriched[1].tweet_type == "quote"
    assert enriched[2].tweet_type == "original"
