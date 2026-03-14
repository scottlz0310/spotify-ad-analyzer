from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from src import db

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test.db"
    db.init_db(path)
    return path


# ---------------------------------------------------------------------------
# init_db
# ---------------------------------------------------------------------------


def test_init_db_creates_file(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "ads.db"
    db.init_db(path)
    assert path.exists()


def test_init_db_idempotent(db_path: Path) -> None:
    db.init_db(db_path)  # second call must not raise
    with db.connect(db_path) as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {str(r["name"]) for r in cursor.fetchall()}
    expected = {"ads", "segments", "transcripts", "voice_embeddings", "llm_analyses"}
    assert expected <= tables


# ---------------------------------------------------------------------------
# ads
# ---------------------------------------------------------------------------


def test_insert_ad_returns_id(db_path: Path) -> None:
    with db.connect(db_path) as conn:
        ad_id = db.insert_ad(
            conn, "spotify_ad_2026-03-14_10-00-00.wav", "2026-03-14T10:00:00Z"
        )
    assert isinstance(ad_id, int)
    assert ad_id > 0


def test_get_ad_by_filename(db_path: Path) -> None:
    filename = "spotify_ad_2026-03-14_10-00-00.wav"
    with db.connect(db_path) as conn:
        _ = db.insert_ad(conn, filename, "2026-03-14T10:00:00Z")
        row = db.get_ad_by_filename(conn, filename)
    assert row is not None
    assert row["filename"] == filename
    assert row["status"] == "pending"
    assert row["error_message"] is None


def test_get_ad_by_filename_not_found(db_path: Path) -> None:
    with db.connect(db_path) as conn:
        row = db.get_ad_by_filename(conn, "nonexistent.wav")
    assert row is None


def test_update_ad_status(db_path: Path) -> None:
    with db.connect(db_path) as conn:
        ad_id = db.insert_ad(
            conn, "spotify_ad_2026-03-14_10-01-00.wav", "2026-03-14T10:01:00Z"
        )
        db.update_ad_status(conn, ad_id, "processing")
        row = db.get_ad_by_filename(conn, "spotify_ad_2026-03-14_10-01-00.wav")
    assert row is not None
    assert row["status"] == "processing"
    assert row["error_message"] is None


def test_update_ad_status_with_error(db_path: Path) -> None:
    with db.connect(db_path) as conn:
        ad_id = db.insert_ad(
            conn, "spotify_ad_2026-03-14_10-02-00.wav", "2026-03-14T10:02:00Z"
        )
        db.update_ad_status(conn, ad_id, "error", error_message="whisper failed")
        row = db.get_ad_by_filename(conn, "spotify_ad_2026-03-14_10-02-00.wav")
    assert row is not None
    assert row["status"] == "error"
    assert row["error_message"] == "whisper failed"


def test_get_ads_by_status(db_path: Path) -> None:
    with db.connect(db_path) as conn:
        _ = db.insert_ad(
            conn, "spotify_ad_2026-03-14_10-03-00.wav", "2026-03-14T10:03:00Z"
        )
        _ = db.insert_ad(
            conn, "spotify_ad_2026-03-14_10-04-00.wav", "2026-03-14T10:04:00Z"
        )
        ad_id = db.insert_ad(
            conn, "spotify_ad_2026-03-14_10-05-00.wav", "2026-03-14T10:05:00Z"
        )
        db.update_ad_status(conn, ad_id, "done")
        pending = db.get_ads_by_status(conn, "pending")
        done = db.get_ads_by_status(conn, "done")
    assert len(pending) == 2
    assert len(done) == 1


# ---------------------------------------------------------------------------
# segments
# ---------------------------------------------------------------------------


def test_insert_and_get_segments(db_path: Path) -> None:
    segs: list[db.SegmentInsert] = [
        {
            "speaker": "SPEAKER_00",
            "text": "Hello world",
            "start_sec": 0.0,
            "end_sec": 1.5,
        },
        {"speaker": "SPEAKER_01", "text": "Hi there", "start_sec": 1.5, "end_sec": 3.0},
    ]
    with db.connect(db_path) as conn:
        ad_id = db.insert_ad(
            conn, "spotify_ad_2026-03-14_11-00-00.wav", "2026-03-14T11:00:00Z"
        )
        db.insert_segments(conn, ad_id, segs)
        rows = db.get_segments(conn, ad_id)
    assert len(rows) == 2
    assert rows[0]["speaker"] == "SPEAKER_00"
    assert rows[0]["text"] == "Hello world"
    assert rows[1]["end_sec"] == 3.0


def test_get_segments_empty(db_path: Path) -> None:
    with db.connect(db_path) as conn:
        ad_id = db.insert_ad(
            conn, "spotify_ad_2026-03-14_11-01-00.wav", "2026-03-14T11:01:00Z"
        )
        rows = db.get_segments(conn, ad_id)
    assert rows == []


# ---------------------------------------------------------------------------
# transcripts
# ---------------------------------------------------------------------------


def test_upsert_and_get_transcript(db_path: Path) -> None:
    with db.connect(db_path) as conn:
        ad_id = db.insert_ad(
            conn, "spotify_ad_2026-03-14_12-00-00.wav", "2026-03-14T12:00:00Z"
        )
        db.upsert_transcript(conn, ad_id, "Buy now!", "ja", "small")
        row = db.get_transcript(conn, ad_id)
    assert row is not None
    assert row["full_text"] == "Buy now!"
    assert row["language"] == "ja"
    assert row["whisper_model"] == "small"


def test_upsert_transcript_replaces(db_path: Path) -> None:
    with db.connect(db_path) as conn:
        ad_id = db.insert_ad(
            conn, "spotify_ad_2026-03-14_12-01-00.wav", "2026-03-14T12:01:00Z"
        )
        db.upsert_transcript(conn, ad_id, "old text", "en", "tiny")
        db.upsert_transcript(conn, ad_id, "new text", "ja", "small")
        row = db.get_transcript(conn, ad_id)
    assert row is not None
    assert row["full_text"] == "new text"


def test_get_transcript_not_found(db_path: Path) -> None:
    with db.connect(db_path) as conn:
        ad_id = db.insert_ad(
            conn, "spotify_ad_2026-03-14_12-02-00.wav", "2026-03-14T12:02:00Z"
        )
        row = db.get_transcript(conn, ad_id)
    assert row is None


# ---------------------------------------------------------------------------
# voice_embeddings
# ---------------------------------------------------------------------------


def test_upsert_and_get_voice_embedding(db_path: Path) -> None:
    embedding = bytes(256)  # 256 zero bytes as placeholder
    with db.connect(db_path) as conn:
        ad_id = db.insert_ad(
            conn, "spotify_ad_2026-03-14_13-00-00.wav", "2026-03-14T13:00:00Z"
        )
        db.upsert_voice_embedding(conn, ad_id, "SPEAKER_00", embedding)
        rows = db.get_voice_embeddings(conn, ad_id)
    assert len(rows) == 1
    assert rows[0]["speaker"] == "SPEAKER_00"
    assert rows[0]["embedding"] == embedding


def test_upsert_voice_embedding_updates_on_conflict(db_path: Path) -> None:
    emb1 = bytes(256)
    emb2 = bytes([1] * 256)
    with db.connect(db_path) as conn:
        ad_id = db.insert_ad(
            conn, "spotify_ad_2026-03-14_13-01-00.wav", "2026-03-14T13:01:00Z"
        )
        db.upsert_voice_embedding(conn, ad_id, "SPEAKER_00", emb1)
        db.upsert_voice_embedding(conn, ad_id, "SPEAKER_00", emb2)
        rows = db.get_voice_embeddings(conn, ad_id)
    assert len(rows) == 1
    assert rows[0]["embedding"] == emb2


def test_get_voice_embeddings_multiple_speakers(db_path: Path) -> None:
    with db.connect(db_path) as conn:
        ad_id = db.insert_ad(
            conn, "spotify_ad_2026-03-14_13-02-00.wav", "2026-03-14T13:02:00Z"
        )
        db.upsert_voice_embedding(conn, ad_id, "SPEAKER_00", bytes(256))
        db.upsert_voice_embedding(conn, ad_id, "SPEAKER_01", bytes(256))
        rows = db.get_voice_embeddings(conn, ad_id)
    assert len(rows) == 2
    speakers = {r["speaker"] for r in rows}
    assert speakers == {"SPEAKER_00", "SPEAKER_01"}


# ---------------------------------------------------------------------------
# llm_analyses
# ---------------------------------------------------------------------------


def test_upsert_and_get_llm_analysis(db_path: Path) -> None:
    with db.connect(db_path) as conn:
        ad_id = db.insert_ad(
            conn, "spotify_ad_2026-03-14_14-00-00.wav", "2026-03-14T14:00:00Z"
        )
        db.upsert_llm_analysis(
            conn,
            ad_id,
            raw_response='{"product":"Acme","type":"CM"}',
            product_name="Acme",
            ad_type="CM",
            summary="Product ad",
            tone="upbeat",
        )
        row = db.get_llm_analysis(conn, ad_id)
    assert row is not None
    assert row["product_name"] == "Acme"
    assert row["ad_type"] == "CM"
    assert row["tone"] == "upbeat"


def test_upsert_llm_analysis_nullable_fields(db_path: Path) -> None:
    with db.connect(db_path) as conn:
        ad_id = db.insert_ad(
            conn, "spotify_ad_2026-03-14_14-01-00.wav", "2026-03-14T14:01:00Z"
        )
        db.upsert_llm_analysis(conn, ad_id, raw_response="{}")
        row = db.get_llm_analysis(conn, ad_id)
    assert row is not None
    assert row["product_name"] is None
    assert row["tone"] is None


def test_get_llm_analysis_not_found(db_path: Path) -> None:
    with db.connect(db_path) as conn:
        ad_id = db.insert_ad(
            conn, "spotify_ad_2026-03-14_14-02-00.wav", "2026-03-14T14:02:00Z"
        )
        row = db.get_llm_analysis(conn, ad_id)
    assert row is None


# ---------------------------------------------------------------------------
# FK cascade
# ---------------------------------------------------------------------------


def test_delete_ad_cascades(db_path: Path) -> None:
    with db.connect(db_path) as conn:
        ad_id = db.insert_ad(
            conn, "spotify_ad_2026-03-14_15-00-00.wav", "2026-03-14T15:00:00Z"
        )
        db.insert_segments(
            conn,
            ad_id,
            [
                {
                    "speaker": "SPEAKER_00",
                    "text": "test",
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                },
            ],
        )
        db.upsert_transcript(conn, ad_id, "test", "en", "small")
        db.upsert_voice_embedding(conn, ad_id, "SPEAKER_00", bytes(256))
        _ = conn.execute("DELETE FROM ads WHERE id = ?", (ad_id,))
        assert db.get_segments(conn, ad_id) == []
        assert db.get_transcript(conn, ad_id) is None
        assert db.get_voice_embeddings(conn, ad_id) == []
