"""Tests for xdigest.render — HTML email generation."""

import pytest
from datetime import datetime

from xdigest.fetch import Tweet
from xdigest.analyze import AnalyzedItem
from xdigest.render import render_digest


def make_analyzed_item(tweet_id, text, username, summary, section, urls=None, key_points=None):
    tweet = Tweet(
        id=tweet_id, text=text, author_id="100", author_username=username,
        author_name=username.title(), created_at="2026-04-13T12:00:00.000Z",
        public_metrics={"like_count": 10}, entities={},
        referenced_tweets=None, urls=urls or [], tweet_type="original",
    )
    return AnalyzedItem(
        tweet_id=tweet_id, tweet=tweet,
        triage_section=section, triage_reason="relevant",
        urls=urls or [], url_types=["article"] * len(urls or []),
        summary=summary, key_points=key_points or [],
        section=section,
    )


@pytest.fixture
def sample_items():
    return [
        make_analyzed_item(
            "1", "Pi is migrating to earendil-works",
            "badlogicgames", "Pi está migrando para @earendilworks no GitHub.",
            "Pi / Earendil",
            urls=["https://github.com/earendil-works/pi-website"],
            key_points=["RFC approved", "Community positive"],
        ),
        make_analyzed_item(
            "2", "How to Build an Agent by Thorsten Ball",
            "thorstenball", "Build a fully functional agent in under 400 lines of Go.",
            "Articles",
            urls=["https://ampcode.com/notes/how-to-build-an-agent"],
        ),
        make_analyzed_item(
            "3", "HITL burnout is real",
            "IntuitMachine", "AI reduces execution work but increases judgment work.",
            "Reflections",
        ),
    ]


def test_render_produces_valid_html(sample_items):
    html = render_digest(
        items=sample_items,
        run_id="2026-04-13T10:00:00",
        total_tweets=390,
        relevant_count=50,
        window_start="10h",
        window_end="19h",
        timezone="BRT",
    )

    assert "<!DOCTYPE html>" in html
    assert "<h2>" in html
    assert "X Digest" in html


def test_render_groups_by_section(sample_items):
    html = render_digest(
        items=sample_items,
        run_id="2026-04-13T10:00:00",
        total_tweets=390,
        relevant_count=50,
    )

    # Sections should appear as h3
    assert "<h3>Pi / Earendil</h3>" in html
    assert "<h3>Articles</h3>" in html
    assert "<h3>Reflections</h3>" in html


def test_render_includes_quick_links(sample_items):
    html = render_digest(
        items=sample_items,
        run_id="2026-04-13T10:00:00",
        total_tweets=390,
        relevant_count=50,
    )

    # Should have an ordered list at top
    assert "<ol>" in html
    assert "ampcode.com" in html


def test_render_includes_item_details(sample_items):
    html = render_digest(
        items=sample_items,
        run_id="2026-04-13T10:00:00",
        total_tweets=390,
        relevant_count=50,
    )

    assert "@badlogicgames" in html
    assert "earendilworks" in html or "earendil-works" in html
    assert "HITL burnout" in html or "judgment work" in html


def test_render_minimal_css():
    """The CSS should be minimal — h5 margin only."""
    html = render_digest(
        items=[],
        run_id="2026-04-13T10:00:00",
        total_tweets=0,
        relevant_count=0,
    )

    assert "h5 { margin-bottom: 0.5em; }" in html
    assert "h5 + p { margin-top: 0; }" in html
    # No colors or backgrounds
    assert "background-color" not in html
    assert "color:" not in html


def test_render_footer():
    html = render_digest(
        items=[],
        run_id="2026-04-13T10:00:00",
        total_tweets=100,
        relevant_count=10,
    )

    assert "Espelho" in html or "xurl" in html
    assert "100 tweets" in html or "Espelho" in html
