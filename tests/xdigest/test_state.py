import pytest
from datetime import datetime, timezone

from xdigest.state import StateDB


@pytest.fixture
def db(tmp_path):
    return StateDB(tmp_path / "test_state.db")


def test_creates_tables(db):
    """DB should have tweets_seen and digests_sent tables after init."""
    tables = db.list_tables()
    assert "tweets_seen" in tables
    assert "digests_sent" in tables


def test_mark_tweet_seen_and_check(db):
    db.mark_tweet_seen("tweet123", digest_run="2026-04-13T10:00:00")
    assert db.is_tweet_seen("tweet123")
    assert not db.is_tweet_seen("tweet999")


def test_mark_tweet_seen_idempotent(db):
    db.mark_tweet_seen("tweet123", digest_run="run1")
    db.mark_tweet_seen("tweet123", digest_run="run2")  # should not raise
    assert db.is_tweet_seen("tweet123")


def test_filter_unseen_tweets(db):
    db.mark_tweet_seen("t1", digest_run="run1")
    db.mark_tweet_seen("t2", digest_run="run1")

    unseen = db.filter_unseen(["t1", "t2", "t3", "t4"])
    assert set(unseen) == {"t3", "t4"}


def test_record_digest_sent(db):
    db.record_digest(
        run_id="2026-04-13T10:00:00",
        tweet_count=42,
        relevant_count=15,
    )
    digests = db.recent_digests(limit=5)
    assert len(digests) == 1
    assert digests[0]["run_id"] == "2026-04-13T10:00:00"
    assert digests[0]["tweet_count"] == 42


def test_recent_digests_ordered_by_recency(db):
    db.record_digest(run_id="run-old", tweet_count=10, relevant_count=5)
    db.record_digest(run_id="run-new", tweet_count=20, relevant_count=8)
    digests = db.recent_digests(limit=5)
    assert digests[0]["run_id"] == "run-new"
    assert digests[1]["run_id"] == "run-old"
