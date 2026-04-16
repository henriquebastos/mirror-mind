"""CLI entry point and checkpoint pipeline for xdigest."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from xdigest.analyze import AnalyzedItem, analyze_tweets
from xdigest.config import Config, load_config
from xdigest.fetch import Tweet, enrich_tweets, fetch_timeline
from xdigest.render import render_digest
from xdigest.send import send_digest
from xdigest.state import StateDB


DEFAULT_BASE_DIR = Path("~/.config/espelho/xdigest/runs").expanduser()


class Pipeline:
    """Checkpoint-based pipeline. Each step writes to a JSON file.
    If it crashes, it resumes from the last completed step.

    All external dependencies are injected via `deps` dict for testability.
    """

    def __init__(
        self,
        config: Config,
        base_dir: Path = DEFAULT_BASE_DIR,
        run_id: Optional[str] = None,
        deps: Optional[dict] = None,
    ):
        self.config = config
        self.deps = deps or {}
        self.run_id = run_id or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        self.run_dir = base_dir / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def save_checkpoint(self, step: str, data: dict | str):
        """Save checkpoint data for a step."""
        path = self.run_dir / f"{step}.json"
        if isinstance(data, str):
            path.with_suffix(".html" if "<html>" in data.lower() else ".json").write_text(data)
        else:
            path.write_text(json.dumps(data, indent=2, default=str))

    def load_checkpoint(self, step: str) -> dict:
        """Load checkpoint data for a step."""
        path = self.run_dir / f"{step}.json"
        return json.loads(path.read_text())

    def is_step_complete(self, step: str) -> bool:
        """Check if a step's checkpoint exists."""
        json_path = self.run_dir / f"{step}.json"
        html_path = self.run_dir / f"{step}.html"
        return json_path.exists() or html_path.exists()

    def run(self):
        """Execute the full pipeline with checkpoint recovery."""
        print(f"[xdigest] Run: {self.run_id}")
        print(f"[xdigest] Dir: {self.run_dir}")

        # Step 1: Fetch
        if not self.is_step_complete("1_fetch"):
            print("[xdigest] Step 1: Fetching timeline...")
            fetch_kwargs = {
                "user_id": self.config.user_id,
                "max_results": self.config.max_results_per_fetch,
            }
            if "run_command" in self.deps:
                fetch_kwargs["run_command"] = self.deps["run_command"]
            if "max_pages" in self.deps:
                fetch_kwargs["max_pages"] = self.deps["max_pages"]
            tweets = fetch_timeline(**fetch_kwargs)
            tweets = enrich_tweets(tweets)
            self.save_checkpoint("1_fetch", {
                "tweets": [_tweet_to_dict(t) for t in tweets],
            })
            print(f"[xdigest]   Fetched {len(tweets)} tweets")
        else:
            print("[xdigest] Step 1: ✓ (cached)")

        fetch_data = self.load_checkpoint("1_fetch")
        tweets = [_dict_to_tweet(d) for d in fetch_data["tweets"]]

        # Step 2: Triage
        if not self.is_step_complete("2_triage"):
            print("[xdigest] Step 2: Triaging...")
            from xdigest.triage import triage_tweets
            triage_kwargs = {
                "tweets": tweets, "interests": self.config.interests,
                "exclude": self.config.exclude, "priority_usernames": self.config.priority_usernames,
            }
            if "run_pi" in self.deps:
                triage_kwargs["run_pi"] = self.deps["run_pi"]
            relevant, triage_data = triage_tweets(**triage_kwargs)
            self.save_checkpoint("2_triage", {
                "relevant": triage_data["relevant"],
                "excluded": triage_data["excluded"],
                "relevant_ids": [t.id for t in relevant],
            })
            print(f"[xdigest]   {len(relevant)} relevant / {len(tweets)} total")
        else:
            print("[xdigest] Step 2: ✓ (cached)")

        triage_data = self.load_checkpoint("2_triage")
        relevant_ids = set(triage_data["relevant_ids"])
        relevant_tweets = [t for t in tweets if t.id in relevant_ids]

        # Step 3: Analyze
        if not self.is_step_complete("3_analyze"):
            print("[xdigest] Step 3: Analyzing content...")
            analyze_kwargs = {"tweets": relevant_tweets, "triage_data": triage_data["relevant"]}
            for key in ("run_pi", "fetch_article", "fetch_captions"):
                if key in self.deps:
                    analyze_kwargs[key] = self.deps[key]
            items = analyze_tweets(**analyze_kwargs)
            self.save_checkpoint("3_analyze", {
                "items": [_item_to_dict(i) for i in items],
            })
            print(f"[xdigest]   Analyzed {len(items)} items")
        else:
            print("[xdigest] Step 3: ✓ (cached)")

        analyze_data = self.load_checkpoint("3_analyze")
        items = [_dict_to_item(d) for d in analyze_data["items"]]

        # Step 4: Render
        if not self.is_step_complete("4_render"):
            print("[xdigest] Step 4: Rendering HTML...")
            html = render_digest(
                items=items,
                run_id=self.run_id,
                total_tweets=len(tweets),
                relevant_count=len(relevant_tweets),
                username=self.config.username,
            )
            (self.run_dir / "4_render.html").write_text(html)
            print("[xdigest]   HTML rendered")
        else:
            print("[xdigest] Step 4: ✓ (cached)")

        html = (self.run_dir / "4_render.html").read_text()

        # Step 5: Send
        if not self.is_step_complete("5_sent"):
            print("[xdigest] Step 5: Sending email...")
            from datetime import date as _date
            date_str = _date.today().strftime("%-d %b %Y")

            send_kwargs = {
                "html": html, "to": self.config.email_to,
                "from_addr": self.config.email_from, "subject": f"X Digest — {date_str}",
            }
            if "run_send" in self.deps:
                send_kwargs["run_command"] = self.deps["run_send"]
            result = send_digest(**send_kwargs)
            self.save_checkpoint("5_sent", {
                "message_id": result.get("id"),
                "thread_id": result.get("threadId"),
            })
            print(f"[xdigest]   Sent! Message ID: {result.get('id')}")
        else:
            print("[xdigest] Step 5: ✓ (cached)")

        # Update state DB
        try:
            db = StateDB(self.config.db_path)
            for t in tweets:
                db.mark_tweet_seen(t.id, digest_run=self.run_id)
            db.record_digest(
                run_id=self.run_id,
                tweet_count=len(tweets),
                relevant_count=len(relevant_tweets),
            )
            db.close()
        except Exception as e:
            print(f"[xdigest] Warning: state DB update failed: {e}")

        print("[xdigest] ✓ Done!")


# --- Serialization helpers ---

def _tweet_to_dict(t: Tweet) -> dict:
    return {
        "id": t.id, "text": t.text, "author_id": t.author_id,
        "author_username": t.author_username, "author_name": t.author_name,
        "created_at": t.created_at, "public_metrics": t.public_metrics,
        "entities": t.entities, "referenced_tweets": t.referenced_tweets,
        "urls": t.urls, "tweet_type": t.tweet_type,
    }


def _dict_to_tweet(d: dict) -> Tweet:
    return Tweet(
        id=d["id"], text=d["text"], author_id=d["author_id"],
        author_username=d["author_username"], author_name=d["author_name"],
        created_at=d["created_at"], public_metrics=d["public_metrics"],
        entities=d["entities"], referenced_tweets=d.get("referenced_tweets"),
        urls=d.get("urls", []), tweet_type=d.get("tweet_type", "original"),
    )


def _item_to_dict(item: AnalyzedItem) -> dict:
    return {
        "tweet_id": item.tweet_id,
        "tweet": _tweet_to_dict(item.tweet),
        "triage_section": item.triage_section,
        "triage_reason": item.triage_reason,
        "urls": item.urls,
        "url_types": item.url_types,
        "summary": item.summary,
        "key_points": item.key_points,
        "section": item.section,
        "quick_title": item.quick_title,
        "fetch_error": item.fetch_error,
    }


def _dict_to_item(d: dict) -> AnalyzedItem:
    tweet = _dict_to_tweet(d["tweet"])
    return AnalyzedItem(
        tweet_id=d["tweet_id"],
        tweet=tweet,
        triage_section=d.get("triage_section", "General"),
        triage_reason=d.get("triage_reason", ""),
        urls=d.get("urls", []),
        url_types=d.get("url_types", []),
        summary=d.get("summary"),
        key_points=d.get("key_points", []),
        section=d.get("section"),
        quick_title=d.get("quick_title"),
        fetch_error=d.get("fetch_error"),
    )


def main():
    """CLI entry point."""
    config = load_config()
    pipeline = Pipeline(config=config)
    pipeline.run()


if __name__ == "__main__":
    main()
