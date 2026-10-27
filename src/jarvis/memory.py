
"""Persistent, local SQLite memory for JARVIS."""

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Memory:
    """One saved memory."""

    id: int
    content: str
    created_at: str


def default_memory_path() -> Path:
    """Return the default XDG data path for JARVIS's memory database."""
    data_home = Path(
        os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
    )
    jarvis_db = data_home / "jarvis" / "memories.sqlite3"
    friday_db = data_home / "friday" / "memories.sqlite3"
    if not jarvis_db.exists() and friday_db.exists():
        return friday_db
    return jarvis_db


class MemoryStore:
    """Save, retrieve, and delete user-approved memories using SQLite."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path if path is not None else default_memory_path()

    def _connect(self) -> sqlite3.Connection:
        """Open the database and ensure its table exists."""
        self.path.parent.mkdir(parents=True, exist_ok=True)

        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.commit()
        return connection

    def save(self, content: str) -> Memory:
        """Save a memory explicitly provided by the user."""
        content = content.strip()
        if not content:
            raise ValueError("Memory cannot be empty.")

        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO memories (content) VALUES (?)",
                (content,),
            )
            row = connection.execute(
                "SELECT id, content, created_at FROM memories WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()

        return Memory(
            id=row["id"],
            content=row["content"],
            created_at=row["created_at"],
        )

    def list_all(self) -> list[Memory]:
        """Return all memories, newest first."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, content, created_at
                FROM memories
                ORDER BY id DESC
                """
            ).fetchall()

        return [
            Memory(
                id=row["id"],
                content=row["content"],
                created_at=row["created_at"],
            )
            for row in rows
        ]



    def search(self, query: str, limit: int = 5) -> list[Memory]:
        """Find memories using identity-aware and keyword matching."""
        import re

        if not isinstance(query, str):
            raise ValueError("Search query must be a string.")

        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("Search limit must be a positive integer.")

        normalized_query = " ".join(
            re.findall(r"\w+", query.lower())
        )

        memories = self.list_all()
        if not normalized_query:
            return []

        # Give identity questions a chance to retrieve relevant saved facts,
        # even when their wording doesn't overlap with the memory content.
        identity_patterns = (
            r"\bwho am i\b",
            r"\bwhat is my name\b",
            r"\bwho is the user\b",
            r"\bwho built you\b",
            r"\bwho made you\b",
            r"\bwho created you\b",
            r"\bwho is building (?:friday|jarvis)\b",
            r"\bwho built (?:friday|jarvis)\b",
            r"\bwho created (?:friday|jarvis)\b",
        )

        identity_query = any(
            re.search(pattern, normalized_query)
            for pattern in identity_patterns
        )

        if identity_query:
            identity_terms = {
                "user", "name", "thoufeek", "building", "built",
                "created", "creator", "developer", "friday", "jarvis",
            }
            identity_matches = []

            for memory in memories:
                content_words = set(
                    re.findall(r"\w+", memory.content.lower())
                )
                score = len(identity_terms & content_words)

                if score:
                    identity_matches.append((score, memory))

            identity_matches.sort(
                key=lambda item: (item[0], item[1].id),
                reverse=True,
            )

            if identity_matches:
                return [
                    memory for _, memory in identity_matches[:limit]
                ]

        stop_words = {
            "what", "which", "who", "where", "when", "why", "how",
            "is", "am", "are", "was", "were", "do", "does", "did",
            "my", "me", "i", "you", "your", "the", "a", "an",
            "called", "use", "using", "tell", "about", "please",
        }

        query_words = {
            word
            for word in re.findall(r"\w+", normalized_query)
            if len(word) > 1 and word not in stop_words
        }

        if not query_words:
            return []

        scored: list[tuple[int, Memory]] = []

        for memory in memories:
            memory_words = {
                word.lower()
                for word in re.findall(r"\w+", memory.content)
            }
            score = len(query_words & memory_words)

            if score:
                scored.append((score, memory))

        scored.sort(key=lambda item: (item[0], item[1].id), reverse=True)
        return [memory for _, memory in scored[:limit]]


    def delete(self, memory_id: int) -> bool:
        """Delete one memory by its ID; return whether it existed."""
        if isinstance(memory_id, bool) or not isinstance(memory_id, int):
            raise ValueError("Memory ID must be an integer.")

        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM memories WHERE id = ?",
                (memory_id,),
            )

        return cursor.rowcount > 0


    def update(self, memory_id: int, content: str) -> Memory | None:
        """Update an existing memory and return it, or None if not found."""
        if isinstance(memory_id, bool) or not isinstance(memory_id, int):
            raise ValueError("Memory ID must be an integer.")

        content = content.strip()
        if not content:
            raise ValueError("Memory cannot be empty.")

        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE memories SET content = ? WHERE id = ?",
                (content, memory_id),
            )

            if cursor.rowcount == 0:
                return None

            row = connection.execute(
                """
                SELECT id, content, created_at
                FROM memories
                WHERE id = ?
                """,
                (memory_id,),
            ).fetchone()

        return Memory(
            id=row["id"],
            content=row["content"],
            created_at=row["created_at"],
        )
