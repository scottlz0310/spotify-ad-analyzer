from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import TYPE_CHECKING, Literal, TypedDict, cast

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

AdStatus = Literal["pending", "processing", "done", "error"]


class AdRow(TypedDict):
    id: int
    filename: str
    recorded_at: str
    status: AdStatus
    error_message: str | None
    created_at: str
    updated_at: str


class SegmentInsert(TypedDict):
    speaker: str
    text: str
    start_sec: float
    end_sec: float


class SegmentRow(TypedDict):
    id: int
    ad_id: int
    speaker: str
    text: str
    start_sec: float
    end_sec: float


class TranscriptRow(TypedDict):
    ad_id: int
    full_text: str
    language: str
    whisper_model: str


class VoiceEmbeddingRow(TypedDict):
    id: int
    ad_id: int
    speaker: str
    embedding: bytes


class LlmAnalysisRow(TypedDict):
    ad_id: int
    product_name: str | None
    ad_type: str | None
    summary: str | None
    tone: str | None
    raw_response: str
    analyzed_at: str


_SCHEMA_SQL = """\
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS ads (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    filename      TEXT    NOT NULL UNIQUE,
    recorded_at   TEXT    NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'pending'
                          CHECK(status IN ('pending','processing','done','error')),
    error_message TEXT,
    created_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS segments (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ad_id     INTEGER NOT NULL REFERENCES ads(id) ON DELETE CASCADE,
    speaker   TEXT    NOT NULL,
    text      TEXT    NOT NULL,
    start_sec REAL    NOT NULL,
    end_sec   REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS transcripts (
    ad_id         INTEGER PRIMARY KEY REFERENCES ads(id) ON DELETE CASCADE,
    full_text     TEXT NOT NULL,
    language      TEXT NOT NULL,
    whisper_model TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS voice_embeddings (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ad_id     INTEGER NOT NULL REFERENCES ads(id) ON DELETE CASCADE,
    speaker   TEXT    NOT NULL,
    embedding BLOB    NOT NULL,
    UNIQUE(ad_id, speaker)
);

CREATE TABLE IF NOT EXISTS llm_analyses (
    ad_id        INTEGER PRIMARY KEY REFERENCES ads(id) ON DELETE CASCADE,
    product_name TEXT,
    ad_type      TEXT,
    summary      TEXT,
    tone         TEXT,
    raw_response TEXT NOT NULL,
    analyzed_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
"""


def init_db(db_path: Path) -> None:
    """Create all tables if they don't exist yet."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        _ = conn.executescript(_SCHEMA_SQL)
    finally:
        conn.close()


@contextmanager
def connect(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """Yield a connection with WAL + FK enabled.

    Auto-commits on success; rolls back on exception.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _ = conn.execute("PRAGMA journal_mode = WAL")
    _ = conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Internal row converters
# ---------------------------------------------------------------------------


def _opt_str(value: object) -> str | None:
    return str(value) if value is not None else None


def _row_to_ad(row: sqlite3.Row) -> AdRow:
    return AdRow(
        id=int(row["id"]),
        filename=str(row["filename"]),
        recorded_at=str(row["recorded_at"]),
        status=cast("AdStatus", row["status"]),
        error_message=_opt_str(row["error_message"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _row_to_segment(row: sqlite3.Row) -> SegmentRow:
    return SegmentRow(
        id=int(row["id"]),
        ad_id=int(row["ad_id"]),
        speaker=str(row["speaker"]),
        text=str(row["text"]),
        start_sec=float(row["start_sec"]),
        end_sec=float(row["end_sec"]),
    )


def _row_to_transcript(row: sqlite3.Row) -> TranscriptRow:
    return TranscriptRow(
        ad_id=int(row["ad_id"]),
        full_text=str(row["full_text"]),
        language=str(row["language"]),
        whisper_model=str(row["whisper_model"]),
    )


def _row_to_voice_embedding(row: sqlite3.Row) -> VoiceEmbeddingRow:
    return VoiceEmbeddingRow(
        id=int(row["id"]),
        ad_id=int(row["ad_id"]),
        speaker=str(row["speaker"]),
        embedding=bytes(row["embedding"]),
    )


def _row_to_llm_analysis(row: sqlite3.Row) -> LlmAnalysisRow:
    return LlmAnalysisRow(
        ad_id=int(row["ad_id"]),
        product_name=_opt_str(row["product_name"]),
        ad_type=_opt_str(row["ad_type"]),
        summary=_opt_str(row["summary"]),
        tone=_opt_str(row["tone"]),
        raw_response=str(row["raw_response"]),
        analyzed_at=str(row["analyzed_at"]),
    )


# ---------------------------------------------------------------------------
# ads
# ---------------------------------------------------------------------------


def insert_ad(conn: sqlite3.Connection, filename: str, recorded_at: str) -> int:
    """Insert a new ad record and return its id."""
    cursor = conn.execute(
        "INSERT INTO ads (filename, recorded_at) VALUES (?, ?)",
        (filename, recorded_at),
    )
    row_id = cursor.lastrowid
    if row_id is None:
        msg = "INSERT into ads returned no lastrowid"
        raise RuntimeError(msg)
    return row_id


def update_ad_status(
    conn: sqlite3.Connection,
    ad_id: int,
    status: AdStatus,
    error_message: str | None = None,
) -> None:
    """Update the processing status (and optional error message) of an ad."""
    _ = conn.execute(
        """
        UPDATE ads
           SET status = ?, error_message = ?,
               updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
         WHERE id = ?
        """,
        (status, error_message, ad_id),
    )


def get_ad_by_filename(conn: sqlite3.Connection, filename: str) -> AdRow | None:
    """Return the ad row matching filename, or None if not found."""
    cursor = conn.execute("SELECT * FROM ads WHERE filename = ?", (filename,))
    row = cursor.fetchone()
    return _row_to_ad(row) if row is not None else None


def get_ads_by_status(conn: sqlite3.Connection, status: AdStatus) -> list[AdRow]:
    """Return all ads with the given status, ordered by recorded_at."""
    cursor = conn.execute(
        "SELECT * FROM ads WHERE status = ? ORDER BY recorded_at",
        (status,),
    )
    return [_row_to_ad(r) for r in cursor.fetchall()]


# ---------------------------------------------------------------------------
# segments
# ---------------------------------------------------------------------------


def insert_segments(
    conn: sqlite3.Connection,
    ad_id: int,
    segments: list[SegmentInsert],
) -> None:
    """Bulk-insert speaker segments for an ad."""
    _ = conn.executemany(
        "INSERT INTO segments "
        "(ad_id, speaker, text, start_sec, end_sec) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            (ad_id, s["speaker"], s["text"], s["start_sec"], s["end_sec"])
            for s in segments
        ],
    )


def get_segments(conn: sqlite3.Connection, ad_id: int) -> list[SegmentRow]:
    """Return all segments for an ad, ordered by start time."""
    cursor = conn.execute(
        "SELECT * FROM segments WHERE ad_id = ? ORDER BY start_sec",
        (ad_id,),
    )
    return [_row_to_segment(r) for r in cursor.fetchall()]


# ---------------------------------------------------------------------------
# transcripts
# ---------------------------------------------------------------------------


def upsert_transcript(
    conn: sqlite3.Connection,
    ad_id: int,
    full_text: str,
    language: str,
    whisper_model: str,
) -> None:
    """Insert or replace the transcript for an ad."""
    _ = conn.execute(
        """
        INSERT OR REPLACE INTO transcripts (ad_id, full_text, language, whisper_model)
        VALUES (?, ?, ?, ?)
        """,
        (ad_id, full_text, language, whisper_model),
    )


def get_transcript(conn: sqlite3.Connection, ad_id: int) -> TranscriptRow | None:
    """Return the transcript for an ad, or None if not found."""
    cursor = conn.execute("SELECT * FROM transcripts WHERE ad_id = ?", (ad_id,))
    row = cursor.fetchone()
    return _row_to_transcript(row) if row is not None else None


# ---------------------------------------------------------------------------
# voice_embeddings
# ---------------------------------------------------------------------------


def upsert_voice_embedding(
    conn: sqlite3.Connection,
    ad_id: int,
    speaker: str,
    embedding: bytes,
) -> None:
    """Insert or update the voice embedding for a speaker in an ad."""
    _ = conn.execute(
        """
        INSERT INTO voice_embeddings (ad_id, speaker, embedding) VALUES (?, ?, ?)
        ON CONFLICT(ad_id, speaker) DO UPDATE SET embedding = excluded.embedding
        """,
        (ad_id, speaker, embedding),
    )


def get_voice_embeddings(
    conn: sqlite3.Connection,
    ad_id: int,
) -> list[VoiceEmbeddingRow]:
    """Return all voice embeddings for an ad."""
    cursor = conn.execute(
        "SELECT * FROM voice_embeddings WHERE ad_id = ? ORDER BY speaker",
        (ad_id,),
    )
    return [_row_to_voice_embedding(r) for r in cursor.fetchall()]


# ---------------------------------------------------------------------------
# llm_analyses
# ---------------------------------------------------------------------------


def upsert_llm_analysis(
    conn: sqlite3.Connection,
    ad_id: int,
    raw_response: str,
    product_name: str | None = None,
    ad_type: str | None = None,
    summary: str | None = None,
    tone: str | None = None,
) -> None:
    """Insert or replace the LLM analysis result for an ad."""
    _ = conn.execute(
        """
        INSERT OR REPLACE INTO llm_analyses
            (ad_id, product_name, ad_type, summary, tone, raw_response)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (ad_id, product_name, ad_type, summary, tone, raw_response),
    )


def get_llm_analysis(conn: sqlite3.Connection, ad_id: int) -> LlmAnalysisRow | None:
    """Return the LLM analysis for an ad, or None if not found."""
    cursor = conn.execute("SELECT * FROM llm_analyses WHERE ad_id = ?", (ad_id,))
    row = cursor.fetchone()
    return _row_to_llm_analysis(row) if row is not None else None
