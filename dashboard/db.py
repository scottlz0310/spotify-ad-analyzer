"""Shared database helpers for the Spotify Ad Analyzer dashboard."""

from __future__ import annotations

import sqlite3
import struct
from pathlib import Path

DB_PATH = Path("/app/data/ads.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_ads(conn: sqlite3.Connection) -> list[dict]:  # type: ignore[type-arg]
    rows = conn.execute("""
        SELECT
            a.id,
            a.filename,
            a.recorded_at,
            t.full_text,
            t.language,
            t.whisper_model,
            COUNT(DISTINCT s.speaker) AS speaker_count,
            MAX(s.end_sec) AS duration_sec
        FROM ads a
        LEFT JOIN transcripts t ON t.ad_id = a.id
        LEFT JOIN segments s ON s.ad_id = a.id
        GROUP BY a.id
        ORDER BY a.id
    """).fetchall()
    return [dict(r) for r in rows]


def get_segments(conn: sqlite3.Connection, ad_id: int) -> list[dict]:  # type: ignore[type-arg]
    rows = conn.execute(
        "SELECT * FROM segments WHERE ad_id=? ORDER BY start_sec", (ad_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_transcript(conn: sqlite3.Connection, ad_id: int) -> dict | None:  # type: ignore[type-arg]
    row = conn.execute("SELECT * FROM transcripts WHERE ad_id=?", (ad_id,)).fetchone()
    return dict(row) if row else None


def get_llm(conn: sqlite3.Connection, ad_id: int) -> dict | None:  # type: ignore[type-arg]
    row = conn.execute("SELECT * FROM llm_analyses WHERE ad_id=?", (ad_id,)).fetchone()
    return dict(row) if row else None


def blob_to_vec(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def get_all_embeddings(
    conn: sqlite3.Connection,
) -> dict[int, list[float]]:
    rows = conn.execute("SELECT ad_id, embedding FROM voice_embeddings").fetchall()
    return {r["ad_id"]: blob_to_vec(r["embedding"]) for r in rows}
