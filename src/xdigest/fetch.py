"""Fetch X timeline via xurl CLI."""

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


XURL_BIN = Path.home() / "go" / "bin" / "xurl"

TWEET_FIELDS = "created_at,public_metrics,entities,referenced_tweets,author_id,conversation_id,in_reply_to_user_id"
EXPANSIONS = "author_id,referenced_tweets.id,referenced_tweets.id.author_id"
USER_FIELDS = "username,name,description"


@dataclass
class Tweet:
    id: str
    text: str
    author_id: str
    author_username: str
    author_name: str
    created_at: str
    public_metrics: dict
    entities: dict
    referenced_tweets: Optional[list] = None
    # Enriched fields
    urls: list[str] = field(default_factory=list)
    tweet_type: str = "original"


def _default_run_command(cmd: str, **kwargs) -> str:
    """Run a shell command and return stdout."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, **kwargs)
    result.check_returncode()
    return result.stdout


def _build_xurl_cmd(user_id: str, max_results: int, pagination_token: str | None = None) -> str:
    """Build the xurl command for timeline fetch."""
    url = (
        f"https://api.x.com/2/users/{user_id}/timelines/reverse_chronological"
        f"?max_results={max_results}"
        f"&tweet.fields={TWEET_FIELDS}"
        f"&expansions={EXPANSIONS}"
        f"&user.fields={USER_FIELDS}"
    )
    if pagination_token:
        url += f"&pagination_token={pagination_token}"
    return f'{XURL_BIN} "{url}"'


def _parse_response(raw_json: str) -> tuple[list[dict], dict[str, dict], str | None]:
    """Parse xurl response into (tweets_data, user_map, next_token)."""
    data = json.loads(raw_json)

    tweets_data = data.get("data", [])
    if not tweets_data:
        return [], {}, None

    # Build user lookup
    users = data.get("includes", {}).get("users", [])
    user_map = {u["id"]: u for u in users}

    next_token = data.get("meta", {}).get("next_token")
    return tweets_data, user_map, next_token


def fetch_timeline(
    user_id: str,
    max_results: int = 100,
    run_command: Callable = _default_run_command,
    max_pages: int = 10,
) -> list[Tweet]:
    """Fetch timeline tweets with pagination. Returns list of Tweet objects.

    Args:
        user_id: X user ID
        max_results: Results per page (max 100)
        run_command: Callable(cmd) -> str. Injected for testing.
        max_pages: Safety limit on pagination
    """
    all_tweets = []
    pagination_token = None

    for _ in range(max_pages):
        cmd = _build_xurl_cmd(user_id, max_results, pagination_token)
        raw = run_command(cmd)
        tweets_data, user_map, next_token = _parse_response(raw)

        if not tweets_data:
            break

        for t in tweets_data:
            user = user_map.get(t.get("author_id", ""), {})
            tweet = Tweet(
                id=t["id"],
                text=t["text"],
                author_id=t.get("author_id", ""),
                author_username=user.get("username", "unknown"),
                author_name=user.get("name", "Unknown"),
                created_at=t.get("created_at", ""),
                public_metrics=t.get("public_metrics", {}),
                entities=t.get("entities", {}),
                referenced_tweets=t.get("referenced_tweets"),
            )
            all_tweets.append(tweet)

        if not next_token:
            break
        pagination_token = next_token

    return all_tweets


def enrich_tweets(tweets: list[Tweet]) -> list[Tweet]:
    """Enrich tweets with extracted URLs and tweet type classification."""
    for tweet in tweets:
        # Extract URLs from entities
        urls = tweet.entities.get("urls", [])
        tweet.urls = [u["expanded_url"] for u in urls if "expanded_url" in u]

        # Classify tweet type
        if tweet.referenced_tweets:
            ref_types = {r["type"] for r in tweet.referenced_tweets}
            if "retweeted" in ref_types:
                tweet.tweet_type = "retweet"
            elif "quoted" in ref_types:
                tweet.tweet_type = "quote"
            elif "replied_to" in ref_types:
                tweet.tweet_type = "reply"
        else:
            tweet.tweet_type = "original"

    return tweets
