"""Unit tests for dashboard/db.py helper functions."""

from __future__ import annotations

import sqlite3
import struct
from typing import TYPE_CHECKING

import numpy as np
import pytest

import dashboard.db as ddb

if TYPE_CHECKING:
    from pathlib import Path
# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE ads (
    id INTEGER PRIMARY KEY,
    filename TEXT NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE segments (
    id INTEGER PRIMARY KEY,
    ad_id INTEGER NOT NULL,
    speaker TEXT NOT NULL,
    text TEXT NOT NULL,
    start_sec REAL NOT NULL,
    end_sec REAL NOT NULL
);
CREATE TABLE transcripts (
    ad_id INTEGER PRIMARY KEY,
    full_text TEXT NOT NULL,
    language TEXT NOT NULL,
    whisper_model TEXT NOT NULL
);
CREATE TABLE llm_analyses (
    ad_id INTEGER PRIMARY KEY,
    product_name TEXT,
    ad_type TEXT,
    summary TEXT,
    tone TEXT,
    raw_response TEXT NOT NULL,
    analyzed_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE voice_embeddings (
    id INTEGER PRIMARY KEY,
    ad_id INTEGER NOT NULL,
    speaker TEXT NOT NULL,
    embedding BLOB NOT NULL
);
"""


def _make_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    _ = conn.executescript(_DDL)
    _ = conn.execute("INSERT INTO ads VALUES (1, 'ad1.wav', '2025-01-01 00:00:00')")
    _ = conn.execute("INSERT INTO ads VALUES (2, 'ad2.wav', '2025-01-02 00:00:00')")
    _ = conn.execute(
        "INSERT INTO segments VALUES (1, 1, 'SPEAKER_00', 'Hello world', 0.0, 3.5)"
    )
    _ = conn.execute(
        "INSERT INTO segments VALUES (2, 1, 'SPEAKER_01', 'Buy now', 3.5, 6.0)"
    )
    _ = conn.execute(
        "INSERT INTO transcripts VALUES (1, 'Hello world Buy now', 'ja', 'tiny')"
    )
    raw_json = '{"raw":1}'
    llm_sql = (
        "INSERT INTO llm_analyses VALUES"
        f" (1,'TestProduct','CM','Great ad','friendly','{raw_json}','2025-01-01')"
    )
    _ = conn.execute(llm_sql)
    vec1 = struct.pack("3f", 1.0, 0.0, 0.0)
    vec2 = struct.pack("3f", 0.0, 1.0, 0.0)
    _ = conn.execute(
        "INSERT INTO voice_embeddings VALUES (1, 1, 'SPEAKER_00', ?)", (vec1,)
    )
    _ = conn.execute(
        "INSERT INTO voice_embeddings VALUES (2, 1, 'SPEAKER_01', ?)", (vec2,)
    )
    conn.commit()
    conn.close()


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test_dashboard.db"
    _make_db(db_path)
    return db_path


@pytest.fixture
def conn(tmp_db: Path):  # noqa: ANN201
    c = sqlite3.connect(tmp_db)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


# ---------------------------------------------------------------------------
# blob_to_vec
# ---------------------------------------------------------------------------


def test_blob_to_vec_roundtrip() -> None:
    blob = struct.pack("3f", 1.0, 2.5, -0.5)
    result = ddb.blob_to_vec(blob)
    assert len(result) == 3
    assert abs(result[0] - 1.0) < 1e-5
    assert abs(result[1] - 2.5) < 1e-5
    assert abs(result[2] - -0.5) < 1e-5


# ---------------------------------------------------------------------------
# get_conn (context manager)
# ---------------------------------------------------------------------------


def test_get_conn_yields_connection(
    tmp_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ddb, "DB_PATH", tmp_db)
    with ddb.get_conn() as c:
        row = c.execute("SELECT COUNT(*) AS n FROM ads").fetchone()
        assert int(row["n"]) == 2  # type: ignore[index]


def test_get_conn_closes_on_exit(tmp_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ddb, "DB_PATH", tmp_db)
    with ddb.get_conn() as c:
        pass
    with pytest.raises(sqlite3.ProgrammingError):
        _ = c.execute("SELECT 1").fetchone()


# ---------------------------------------------------------------------------
# get_ads
# ---------------------------------------------------------------------------


def test_get_ads_returns_all(conn: sqlite3.Connection) -> None:
    ads = ddb.get_ads(conn)
    assert len(ads) == 2
    assert ads[0]["id"] == 1
    assert ads[0]["filename"] == "ad1.wav"


def test_get_ads_speaker_count(conn: sqlite3.Connection) -> None:
    ads = ddb.get_ads(conn)
    ad1 = next(a for a in ads if a["id"] == 1)
    assert ad1["speaker_count"] == 2


def test_get_ads_no_transcript(conn: sqlite3.Connection) -> None:
    ads = ddb.get_ads(conn)
    ad2 = next(a for a in ads if a["id"] == 2)
    assert ad2["full_text"] is None


# ---------------------------------------------------------------------------
# get_segments
# ---------------------------------------------------------------------------


def test_get_segments(conn: sqlite3.Connection) -> None:
    segs = ddb.get_segments(conn, 1)
    assert len(segs) == 2
    assert segs[0]["speaker"] == "SPEAKER_00"
    assert segs[1]["speaker"] == "SPEAKER_01"


def test_get_segments_empty(conn: sqlite3.Connection) -> None:
    segs = ddb.get_segments(conn, 2)
    assert segs == []


# ---------------------------------------------------------------------------
# get_transcript
# ---------------------------------------------------------------------------


def test_get_transcript(conn: sqlite3.Connection) -> None:
    t = ddb.get_transcript(conn, 1)
    assert t is not None
    assert t["full_text"] == "Hello world Buy now"
    assert t["language"] == "ja"


def test_get_transcript_missing(conn: sqlite3.Connection) -> None:
    t = ddb.get_transcript(conn, 99)
    assert t is None


# ---------------------------------------------------------------------------
# get_llm
# ---------------------------------------------------------------------------


def test_get_llm(conn: sqlite3.Connection) -> None:
    llm = ddb.get_llm(conn, 1)
    assert llm is not None
    assert llm["product_name"] == "TestProduct"
    assert llm["ad_type"] == "CM"


def test_get_llm_missing(conn: sqlite3.Connection) -> None:
    llm = ddb.get_llm(conn, 99)
    assert llm is None


# ---------------------------------------------------------------------------
# get_all_embeddings (multi-speaker averaging)
# ---------------------------------------------------------------------------


def test_get_all_embeddings_averages_speakers(conn: sqlite3.Connection) -> None:
    embeddings = ddb.get_all_embeddings(conn)
    assert 1 in embeddings
    vec = embeddings[1]
    expected = np.mean([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], axis=0).tolist()
    assert len(vec) == 3
    for a, b in zip(vec, expected, strict=True):
        assert abs(a - b) < 1e-5


def test_get_all_embeddings_no_data(conn: sqlite3.Connection) -> None:
    _ = conn.execute("DELETE FROM voice_embeddings")
    conn.commit()
    embeddings = ddb.get_all_embeddings(conn)
    assert embeddings == {}
