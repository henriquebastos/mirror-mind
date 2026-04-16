"""LLM-based tweet triage via pi CLI."""

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from xdigest.fetch import Tweet


PI_BIN = "pi"


def _default_run_pi(prompt: str, model: str = "claude-sonnet-4-20250514") -> str:
    """Run pi CLI with a prompt and return the response text.
    Uses a temp file for the prompt to avoid stdin/pipe issues with large prompts.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(prompt)
        prompt_file = f.name

    try:
        result = subprocess.run(
            [PI_BIN, "--model", model, "--print",
             "--no-tools", "--no-session", "--no-extensions", "--no-skills",
             f"@{prompt_file}"],
            capture_output=True,
            text=True,
        )
        result.check_returncode()
        return result.stdout.strip()
    finally:
        Path(prompt_file).unlink(missing_ok=True)


def build_triage_prompt(
    tweets: list[Tweet],
    interests: list[str],
    exclude: list[str],
    priority_usernames: set[str],
) -> str:
    """Build the triage prompt for the LLM."""
    lines = [
        "You are a tweet relevance filter for a Distinguished Engineer.",
        "Be SELECTIVE. Quality over quantity. Only include tweets with real signal.",
        "",
        "## Interests (INCLUDE if clearly relevant):",
        *[f"- {i}" for i in interests],
        "",
        "## Exclude (SKIP these):",
        *[f"- {e}" for e in exclude],
        "- Pure retweets (RT) from non-priority accounts UNLESS the original content is exceptional",
        "- Replies that are just agreement/acknowledgment without adding insight",
        "- Short opinions without substance or context",
        "- Sponsored content or promotional announcements",
        "- Vague references that don't provide enough info to summarize",
        "",
        "## Instructions:",
        "Classify each tweet as relevant or excluded.",
        "For relevant tweets, assign a section name (e.g. 'Pi / Earendil', 'Agents', 'Tools', etc.).",
        "Tweets from PRIORITY accounts should almost always be relevant.",
        "Prefer tweets that have: links to articles/repos/videos, specific technical details, original insights, or breaking news.",
        "Group related tweets about the same topic — if 3 people RT the same thing, include only the most informative version.",
        "",
        "Respond with JSON only:",
        '{"relevant": [{"id": "...", "reason": "...", "section": "..."}], "excluded": [{"id": "...", "reason": "..."}]}',
        "",
        "## Tweets:",
        "",
    ]

    for t in tweets:
        priority = " [PRIORITY]" if t.author_username in priority_usernames else ""
        urls_str = f" URLs: {', '.join(t.urls)}" if t.urls else ""
        lines.append(
            f"[{t.id}] @{t.author_username}{priority} ({t.tweet_type}): {t.text}{urls_str}"
        )

    return "\n".join(lines)


def parse_triage_response(response: str) -> tuple[list[dict], list[dict]]:
    """Parse LLM triage response. Returns (relevant, excluded)."""
    # Strip markdown code fences if present
    text = response.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        text = "\n".join(lines)

    if not text:
        return [], []

    # Try to find JSON in the response
    start = text.find("{")
    if start == -1:
        return [], []
    # Find matching closing brace
    depth = 0
    end = start
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    text = text[start:end]

    data = json.loads(text)
    return data.get("relevant", []), data.get("excluded", [])


def triage_tweets(
    tweets: list[Tweet],
    interests: list[str],
    exclude: list[str],
    priority_usernames: set[str],
    run_pi: Callable = _default_run_pi,
    model: str = "claude-sonnet-4-20250514",
) -> tuple[list[Tweet], dict]:
    """Filter tweets by relevance using LLM.

    Returns:
        (relevant_tweets, triage_data) where triage_data has 'relevant' and 'excluded' lists.
    """
    if not tweets:
        return [], {"relevant": [], "excluded": []}

    prompt = build_triage_prompt(tweets, interests, exclude, priority_usernames)
    response = run_pi(prompt, model=model)
    relevant_items, excluded_items = parse_triage_response(response)

    relevant_ids = {r["id"] for r in relevant_items}

    # Force-include priority accounts
    tweet_map = {t.id: t for t in tweets}
    for t in tweets:
        if t.author_username in priority_usernames and t.id not in relevant_ids:
            relevant_ids.add(t.id)
            relevant_items.append({
                "id": t.id,
                "reason": f"Priority account: @{t.author_username}",
                "section": "Priority",
            })

    relevant_tweets = [tweet_map[tid] for tid in relevant_ids if tid in tweet_map]

    return relevant_tweets, {"relevant": relevant_items, "excluded": excluded_items}
