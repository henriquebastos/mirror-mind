"""Content analysis — fetch articles/videos/repos, summarize via pi CLI."""

import json
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Optional

from xdigest.fetch import Tweet

MAX_WORKERS = 5  # parallel pi calls


PI_BIN = "pi"


@dataclass
class AnalyzedItem:
    tweet_id: str
    tweet: Tweet
    triage_section: str
    triage_reason: str
    urls: list[str] = field(default_factory=list)
    url_types: list[str] = field(default_factory=list)
    summary: Optional[str] = None
    key_points: list[str] = field(default_factory=list)
    section: Optional[str] = None
    quick_title: Optional[str] = None
    fetch_error: Optional[str] = None
    raw_content: Optional[str] = None


# --- URL Classification ---

def classify_url(url: str) -> str:
    """Classify a URL into type: github_repo, youtube, article, x_post, image."""
    if re.match(r"https?://(www\.)?github\.com/[^/]+/[^/]+", url):
        return "github_repo"
    if re.match(r"https?://(www\.)?(youtube\.com/watch|youtu\.be/)", url):
        return "youtube"
    if re.match(r"https?://(x\.com|twitter\.com)/[^/]+/status/", url):
        return "x_post"
    if re.match(r"https?://pbs\.twimg\.com/media/", url):
        return "image"
    return "article"


# --- HTML Stripping ---

class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._text = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer", "header"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer", "header"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            self._text.append(data.strip())

    def get_text(self) -> str:
        return "\n".join(line for line in self._text if line)


def _strip_html(html: str) -> str:
    stripper = _HTMLStripper()
    stripper.feed(html)
    return stripper.get_text()


# --- Content Fetchers ---

def _default_curl(url: str) -> str:
    result = subprocess.run(
        ["curl", "-sL", "--max-time", "15", url],
        capture_output=True, text=True,
    )
    return result.stdout


def _default_ytdlp(url: str) -> str:
    result = subprocess.run(
        ["yt-dlp", "--write-auto-sub", "--skip-download", "--sub-lang", "en",
         "--sub-format", "vtt", "-o", "-", "--print", "%(subtitles)s", url],
        capture_output=True, text=True,
    )
    return result.stdout


def fetch_article_text(url: str, run_curl: Callable = _default_curl) -> str:
    """Fetch URL and return stripped text content."""
    html = run_curl(url)
    return _strip_html(html)


def fetch_video_captions(url: str, run_ytdlp: Callable = _default_ytdlp) -> str:
    """Fetch video captions/transcript."""
    return run_ytdlp(url)


# --- LLM Prompts ---

def _default_run_pi(prompt: str, model: str = "claude-sonnet-4-20250514") -> str:
    """Run pi CLI with a temp file prompt. Uses --no-tools --no-session for speed."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(prompt)
        prompt_file = f.name

    try:
        result = subprocess.run(
            [PI_BIN, "--model", model, "--print",
             "--no-tools", "--no-session", "--no-extensions", "--no-skills",
             f"@{prompt_file}"],
            capture_output=True, text=True,
        )
        result.check_returncode()
        return result.stdout.strip()
    finally:
        Path(prompt_file).unlink(missing_ok=True)


ANALYSIS_RULES = """
## Rules
- Summary must be DENSE and COMPLETE — the reader should NOT need to visit the original.
- DO NOT just echo the tweet text. Explain what it means, why it matters, what the takeaway is.
- If article/page content is provided, summarize the ARTICLE, not just the tweet.
- Include all key facts, arguments, technical details, and takeaways.
- For videos, include timestamps as YouTube links (&t=X).
- Content in English stays English. Portuguese stays Portuguese. Other languages → English.
- Simple tweets (opinions, one-liners) get short summaries. Tweets linking to articles/repos get detailed ones.
- key_points should be substantive bullet points, not generic.
- Start the summary with a **bold lead sentence** (use **markdown bold**) capturing the core point.
- If the tweet has URLs, add a 'quick_title': short editorial title for quick-links (e.g. 'How to Build an Agent — Amp').
- Suggest a section name for grouping (e.g. 'Pi / Earendil', 'Agents', 'Tools', etc.).
"""


def build_analysis_prompt(tweet: Tweet, content: str | None = None, url: str | None = None, url_type: str | None = None) -> str:
    """Build analysis prompt for a single tweet with optional fetched content."""
    parts = [
        "You are writing a dense technical digest entry for a Distinguished Engineer.",
        "",
        f"## Tweet",
        f"@{tweet.author_username}: {tweet.text}",
    ]

    if url:
        parts.append(f"URL: {url} (type: {url_type})")

    if content:
        parts.append("")
        parts.append("## Fetched Content")
        parts.append(content[:15000])

    parts.append("")
    parts.append(ANALYSIS_RULES)
    parts.append("")
    parts.append('Respond with JSON only:')
    parts.append('{"summary": "**Lead.** Details...", "key_points": ["..."], "section": "...", "quick_title": "optional"}')

    return "\n".join(parts)


# --- Main Analysis ---

def _fetch_content_for_item(
    item: AnalyzedItem,
    fetch_article: Callable,
    fetch_captions: Callable,
) -> str | None:
    """Fetch content for the first actionable URL on an item. Returns content or None."""
    for url, url_type in zip(item.urls, item.url_types):
        if url_type in ("x_post", "image"):
            continue
        try:
            if url_type == "youtube":
                return fetch_captions(url)
            else:
                raw = fetch_article(url)
                return _strip_html(raw) if "<" in raw else raw
        except Exception as e:
            item.fetch_error = str(e)
            return None
    return None


def _analyze_single_item(
    item: AnalyzedItem,
    content: str | None,
    run_pi: Callable,
    model: str,
) -> None:
    """Analyze a single item via LLM. Mutates item in place."""
    # Find the first actionable URL for context
    url = None
    url_type = None
    for u, ut in zip(item.urls, item.url_types):
        if ut not in ("x_post", "image"):
            url, url_type = u, ut
            break

    prompt = build_analysis_prompt(item.tweet, content=content, url=url, url_type=url_type)
    try:
        response = run_pi(prompt, model=model)
        text = _extract_json(response)
        data = json.loads(text)
        item.summary = data.get("summary", item.tweet.text)
        item.key_points = data.get("key_points", [])
        item.section = data.get("section", item.triage_section)
        item.quick_title = data.get("quick_title")
    except Exception as e:
        if not item.fetch_error:
            item.fetch_error = f"LLM error: {e}"
        item.summary = item.tweet.text


def analyze_tweets(
    tweets: list[Tweet],
    triage_data: list[dict],
    run_pi: Callable = _default_run_pi,
    fetch_article: Callable = _default_curl,
    fetch_captions: Callable = _default_ytdlp,
    model: str = "claude-sonnet-4-20250514",
    max_workers: int = MAX_WORKERS,
) -> list[AnalyzedItem]:
    """Analyze relevant tweets — fetch content and summarize via LLM, in parallel.

    Phase 1: Fetch URL content in parallel (curl/yt-dlp).
    Phase 2: Analyze each tweet via its own pi call in parallel.
    All external dependencies are injected for testability.
    """
    triage_map = {t["id"]: t for t in triage_data}
    items = []

    # Build items and classify URLs
    for tweet in tweets:
        triage = triage_map.get(tweet.id, {})
        item = AnalyzedItem(
            tweet_id=tweet.id,
            tweet=tweet,
            triage_section=triage.get("section", "General"),
            triage_reason=triage.get("reason", ""),
        )
        for url in tweet.urls:
            item.urls.append(url)
            item.url_types.append(classify_url(url))
        items.append(item)

    if not items:
        return []

    # Phase 1: Fetch content in parallel
    contents: dict[str, str | None] = {}

    def _fetch_one(item: AnalyzedItem) -> tuple[str, str | None]:
        return item.tweet_id, _fetch_content_for_item(item, fetch_article, fetch_captions)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for tweet_id, content in pool.map(lambda i: _fetch_one(i), items):
            if content:
                contents[tweet_id] = content

    # Phase 2: Analyze each tweet in parallel (one pi call per tweet)
    def _analyze_one(item: AnalyzedItem) -> AnalyzedItem:
        _analyze_single_item(item, contents.get(item.tweet_id), run_pi, model)
        return item

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        items = list(pool.map(_analyze_one, items))

    return items


def _extract_json(text: str) -> str:
    """Extract JSON from LLM response, handling markdown fences and preamble."""
    text = text.strip()
    # Strip ```json ... ``` fences
    if "```" in text:
        # Find content between first ``` and last ```
        parts = text.split("```")
        # parts[0] = preamble, parts[1] = json/content, parts[2+] = rest
        if len(parts) >= 3:
            content = parts[1]
            # Remove language tag (e.g. 'json\n')
            if content.startswith(("json", "JSON")):
                content = content[4:]
            return content.strip()

    # Find first [ or { for JSON start
    for i, ch in enumerate(text):
        if ch in "[{":
            return text[i:]

    return text
