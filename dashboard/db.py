"""Shared database helpers for the Spotify Ad Analyzer dashboard."""

from __future__ import annotations

import sqlite3
import struct
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from collections.abc import Generator

import numpy as np

DB_PATH = Path("/app/data/ads.db")


class AdSummaryRow(TypedDict):
    id: int
    filename: str
    recorded_at: str
    full_text: str | None
    language: str | None
    whisper_model: str | None
    speaker_count: int
    duration_sec: float | None


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


class LlmAnalysisRow(TypedDict):
    ad_id: int
    product_name: str | None
    ad_type: str | None
    summary: str | None
    tone: str | None
    raw_response: str
    analyzed_at: str


@contextmanager
def get_conn() -> Generator[sqlite3.Connection, None, None]:
    """Yield a SQLite connection, always closing it on exit."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _row_to_ad_summary(row: sqlite3.Row) -> AdSummaryRow:
    return AdSummaryRow(
        id=int(row["id"]),
        filename=str(row["filename"]),
        recorded_at=str(row["recorded_at"]),
        full_text=str(row["full_text"]) if row["full_text"] is not None else None,
        language=str(row["language"]) if row["language"] is not None else None,
        whisper_model=str(row["whisper_model"])
        if row["whisper_model"] is not None
        else None,
        speaker_count=int(row["speaker_count"]),
        duration_sec=float(row["duration_sec"])
        if row["duration_sec"] is not None
        else None,
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


def _row_to_llm_analysis(row: sqlite3.Row) -> LlmAnalysisRow:
    opt = lambda v: str(v) if v is not None else None  # noqa: E731
    return LlmAnalysisRow(
        ad_id=int(row["ad_id"]),
        product_name=opt(row["product_name"]),
        ad_type=opt(row["ad_type"]),
        summary=opt(row["summary"]),
        tone=opt(row["tone"]),
        raw_response=str(row["raw_response"]),
        analyzed_at=str(row["analyzed_at"]),
    )


def get_ads(conn: sqlite3.Connection) -> list[AdSummaryRow]:
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
    return [_row_to_ad_summary(r) for r in rows]


def get_segments(conn: sqlite3.Connection, ad_id: int) -> list[SegmentRow]:
    rows = conn.execute(
        "SELECT * FROM segments WHERE ad_id=? ORDER BY start_sec", (ad_id,)
    ).fetchall()
    return [_row_to_segment(r) for r in rows]


def get_transcript(conn: sqlite3.Connection, ad_id: int) -> TranscriptRow | None:
    row = conn.execute("SELECT * FROM transcripts WHERE ad_id=?", (ad_id,)).fetchone()
    return _row_to_transcript(row) if row else None


def get_llm(conn: sqlite3.Connection, ad_id: int) -> LlmAnalysisRow | None:
    row = conn.execute("SELECT * FROM llm_analyses WHERE ad_id=?", (ad_id,)).fetchone()
    return _row_to_llm_analysis(row) if row else None


def blob_to_vec(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def get_all_embeddings(
    conn: sqlite3.Connection,
) -> dict[int, list[float]]:
    """Return one mean embedding vector per ad_id, averaged across speakers."""
    rows = conn.execute("SELECT ad_id, embedding FROM voice_embeddings").fetchall()
    by_ad: dict[int, list[list[float]]] = {}
    for r in rows:
        by_ad.setdefault(int(r["ad_id"]), []).append(blob_to_vec(r["embedding"]))
    return {ad_id: np.mean(vecs, axis=0).tolist() for ad_id, vecs in by_ad.items()}
