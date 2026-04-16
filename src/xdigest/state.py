"""SQLite state for xdigest — tracks seen tweets and sent digests."""

import sqlite3
from pathlib import Path


class StateDB:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS tweets_seen (
                tweet_id TEXT PRIMARY KEY,
                digest_run TEXT NOT NULL,
                seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS digests_sent (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL UNIQUE,
                tweet_count INTEGER NOT NULL,
                relevant_count INTEGER NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

    def list_tables(self) -> list[str]:
        cur = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        return [row["name"] for row in cur.fetchall()]

    def mark_tweet_seen(self, tweet_id: str, digest_run: str):
        self._conn.execute(
            "INSERT OR IGNORE INTO tweets_seen (tweet_id, digest_run) VALUES (?, ?)",
            (tweet_id, digest_run),
        )
        self._conn.commit()

    def is_tweet_seen(self, tweet_id: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM tweets_seen WHERE tweet_id = ?", (tweet_id,)
        )
        return cur.fetchone() is not None

    def filter_unseen(self, tweet_ids: list[str]) -> list[str]:
        if not tweet_ids:
            return []
        placeholders = ",".join("?" * len(tweet_ids))
        cur = self._conn.execute(
            f"SELECT tweet_id FROM tweets_seen WHERE tweet_id IN ({placeholders})",
            tweet_ids,
        )
        seen = {row["tweet_id"] for row in cur.fetchall()}
        return [tid for tid in tweet_ids if tid not in seen]

    def record_digest(self, run_id: str, tweet_count: int, relevant_count: int):
        self._conn.execute(
            "INSERT OR REPLACE INTO digests_sent (run_id, tweet_count, relevant_count) VALUES (?, ?, ?)",
            (run_id, tweet_count, relevant_count),
        )
        self._conn.commit()

    def recent_digests(self, limit: int = 10) -> list[dict]:
        cur = self._conn.execute(
            "SELECT run_id, tweet_count, relevant_count, sent_at FROM digests_sent ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]

    def close(self):
        self._conn.close()
