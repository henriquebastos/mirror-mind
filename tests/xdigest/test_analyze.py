"""Tests for xdigest.analyze — content analysis via pi CLI."""

import json
import pytest

from xdigest.fetch import Tweet
from xdigest.analyze import (
    classify_url,
    analyze_tweets,
    AnalyzedItem,
    build_analysis_prompt,
    fetch_article_text,
    fetch_video_captions,
)


def make_tweet(id, text, username="alice", urls=None, **kw):
    return Tweet(
        id=id, text=text, author_id="100", author_username=username,
        author_name=username.title(), created_at="2026-04-13T12:00:00.000Z",
        public_metrics={"like_count": 5}, entities={},
        referenced_tweets=None, urls=urls or [], tweet_type="original",
    )


class TestClassifyUrl:
    def test_github_repo(self):
        assert classify_url("https://github.com/user/repo") == "github_repo"
        assert classify_url("https://github.com/user/repo/tree/main") == "github_repo"

    def test_youtube_video(self):
        assert classify_url("https://www.youtube.com/watch?v=abc123") == "youtube"
        assert classify_url("https://youtu.be/abc123") == "youtube"

    def test_article(self):
        assert classify_url("https://example.com/blog/post") == "article"
        assert classify_url("https://ampcode.com/notes/how-to-build-an-agent") == "article"

    def test_x_url(self):
        assert classify_url("https://x.com/user/status/123") == "x_post"
        assert classify_url("https://twitter.com/user/status/123") == "x_post"

    def test_image(self):
        assert classify_url("https://pbs.twimg.com/media/abc.jpg") == "image"


class TestFetchArticleText:
    def test_returns_stripped_text(self):
        def fake_curl(url):
            return "<html><body><h1>Title</h1><p>Content here</p></body></html>"

        text = fetch_article_text("https://example.com/article", run_curl=fake_curl)
        assert "Title" in text
        assert "Content" in text
        assert "<html>" not in text


class TestFetchVideoCaptions:
    def test_returns_captions(self):
        def fake_ytdlp(url):
            return "00:00 Hello\n00:05 World\n00:10 End"

        captions = fetch_video_captions("https://youtube.com/watch?v=abc", run_ytdlp=fake_ytdlp)
        assert "Hello" in captions
        assert "World" in captions


class TestBuildAnalysisPrompt:
    def test_includes_tweet_context(self):
        tweet = make_tweet("1", "Great article about agents", urls=["https://example.com/agents"])
        prompt = build_analysis_prompt(
            tweet=tweet,
            content="Article content about AI agents and orchestration...",
            url="https://example.com/agents",
            url_type="article",
        )
        assert "agents" in prompt.lower()
        assert "example.com" in prompt


class TestAnalyzeTweets:
    def test_analyzes_tweets_with_urls(self):
        tweets = [
            make_tweet("1", "Check this", urls=["https://example.com/article"]),
            make_tweet("2", "Just a thought, no links"),
        ]
        triage_data = [
            {"id": "1", "reason": "AI article", "section": "Articles"},
            {"id": "2", "reason": "Good insight", "section": "Reflections"},
        ]

        def fake_pi(prompt, **kwargs):
            # Per-tweet response
            if "Check this" in prompt:
                return json.dumps({"summary": "Dense summary of the article about AI agents.",
                    "key_points": ["Point 1", "Point 2"], "section": "Agents"})
            return json.dumps({"summary": "A thought about the state of things.",
                "key_points": [], "section": "Reflections"})

        def fake_curl(url):
            return "<html><body><p>Article about AI agents</p></body></html>"

        results = analyze_tweets(
            tweets=tweets,
            triage_data=triage_data,
            run_pi=fake_pi,
            fetch_article=fake_curl,
            fetch_captions=lambda url: "",
        )

        assert len(results) == 2
        item1 = next(r for r in results if r.tweet_id == "1")
        assert item1.summary is not None
        assert "AI agents" in item1.summary

        item2 = next(r for r in results if r.tweet_id == "2")
        assert item2 is not None

    def test_handles_fetch_failure_gracefully(self):
        tweets = [make_tweet("1", "Link here", urls=["https://example.com/broken"])]
        triage_data = [{"id": "1", "reason": "Relevant", "section": "General"}]

        def fake_pi(prompt, **kwargs):
            return json.dumps({"summary": "Tweet about a broken link.",
                "key_points": [], "section": "General"})

        def failing_curl(url):
            raise Exception("Connection refused")

        results = analyze_tweets(
            tweets=tweets,
            triage_data=triage_data,
            run_pi=fake_pi,
            fetch_article=failing_curl,
            fetch_captions=lambda url: "",
        )

        assert len(results) == 1
        assert results[0].fetch_error is not None
