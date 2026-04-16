"""Render HTML email digest from analyzed items."""

from collections import OrderedDict
from datetime import datetime
import re
from html import escape
from typing import Optional

from xdigest.analyze import AnalyzedItem


def _md_to_html(text: str) -> str:
    """Convert minimal markdown (bold) to HTML after escaping."""
    # First escape HTML, then convert **bold** to <strong>
    escaped = escape(text)
    escaped = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', escaped)
    return escaped


def render_digest(
    items: list[AnalyzedItem],
    run_id: str,
    total_tweets: int,
    relevant_count: int,
    window_start: str = "",
    window_end: str = "",
    timezone: str = "BRT",
    username: str = "",
) -> str:
    """Render analyzed items into an HTML email digest.

    Follows the template pattern from template_reference.html:
    - h2 title, h3 sections, h5 item headers
    - Quick links at top
    - Minimal CSS (h5 margins only)
    - No colors/backgrounds
    """
    # Parse date from run_id
    try:
        # Handle both ISO format and custom format like test-1234567890
        clean = run_id.replace("T", " ").replace("Z", "")
        # Try ISO first
        dt = datetime.fromisoformat(clean)
        date_str = dt.strftime("%-d %b %Y")
    except (ValueError, AttributeError):
        from datetime import date
        date_str = date.today().strftime("%-d %b %Y")

    # Group items by section, preserving insertion order
    sections: dict[str, list[AnalyzedItem]] = OrderedDict()
    for item in items:
        section = item.section or item.triage_section or "General"
        sections.setdefault(section, []).append(item)

    # Build quick links (items with URLs that are articles/repos/videos)
    quick_links = []
    seen_urls = set()
    for item in items:
        for url, url_type in zip(item.urls, item.url_types):
            if url_type in ("x_post", "image") or url in seen_urls:
                continue
            seen_urls.add(url)
            # Use quick_title if available, otherwise first line of summary
            label = item.quick_title or (item.summary or item.tweet.text).split("\n")[0][:100]
            # Strip markdown bold from label
            label = label.replace("**", "")
            author = f"@{item.tweet.author_username}"
            quick_links.append((url, label, author))
            break  # One link per item

    # Window info
    window_info = ""
    if window_start and window_end:
        window_info = f"{window_start}–{window_end} {timezone} · "

    # Render HTML
    parts = [
        '<!DOCTYPE html>',
        '<html>',
        '<head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<style>h5 { margin-bottom: 0.5em; } h5 + p { margin-top: 0; }</style>',
        '</head>',
        '<body>',
        '',
        f'<h2>X Digest — {date_str}</h2>',
        f'<p><small>{window_info}{total_tweets} tweets · ~{relevant_count} relevantes</small></p>',
    ]

    # Quick links
    if quick_links:
        parts.append('')
        parts.append('<ol>')
        for url, label, author in quick_links:
            parts.append(f'<li><a href="{escape(url)}">{escape(label)}</a> — {escape(author)}</li>')
        parts.append('</ol>')

    parts.append('')
    parts.append('<hr>')

    # Sections
    for section_name, section_items in sections.items():
        parts.append('')
        parts.append(f'<h3>{escape(section_name)}</h3>')
        parts.append('')

        for item in section_items:
            tweet = item.tweet
            tweet_url = f"https://x.com/{tweet.author_username}/status/{tweet.id}"

            # Timestamps
            try:
                tweet_dt = datetime.fromisoformat(tweet.created_at.replace("Z", "+00:00"))
                time_str = tweet_dt.strftime("%-d %b, %H:%M")
            except (ValueError, AttributeError):
                time_str = tweet.created_at

            # Keywords from section
            keywords = item.triage_reason if item.triage_reason else ""

            # h5 header: @username at timestamp · keywords
            header = f'<h5><a href="https://x.com/{escape(tweet.author_username)}">@{escape(tweet.author_username)}</a>'
            header += f' at <a href="{escape(tweet_url)}">{escape(time_str)}</a>'
            if keywords:
                header += f' · <i>{escape(keywords)}</i>'
            header += '</h5>'
            parts.append(header)

            # Summary
            if item.summary:
                parts.append(f'<p>{_md_to_html(item.summary)}</p>')

            # Key points
            if item.key_points:
                parts.append('<ul>')
                for point in item.key_points:
                    parts.append(f'<li>{escape(point)}</li>')
                parts.append('</ul>')

    # Footer
    parts.append('')
    parts.append('<hr>')
    parts.append('')
    parts.append(f'<p><small>Gerado pelo Espelho · xurl · timeline de @{escape(username)}<br>')
    parts.append(f'{escape(run_id)} · {total_tweets} tweets</small></p>')
    parts.append('')
    parts.append('</body>')
    parts.append('</html>')

    return '\n'.join(parts)
