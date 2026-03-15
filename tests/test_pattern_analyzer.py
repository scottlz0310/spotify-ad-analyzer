"""Tests for src/pattern_analyzer.py — all use a tmp_path on-disk SQLite file."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import numpy as np
import pytest

from src import db
from src.embedder import embedding_to_blob
from src.pattern_analyzer import (
    PatternReport,
    ad_type_distribution,
    detect_repeat_ads,
    hourly_frequency,
    main,
    report,
    tone_distribution,
)

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    return db_path


def _insert_done_ad(
    conn: sqlite3.Connection,
    filename: str,
    recorded_at: str = "2026-01-01T12:00:00Z",
) -> int:
    cur = conn.execute(
        "INSERT INTO ads (filename, recorded_at, status) VALUES (?, ?, 'done')",
        (filename, recorded_at),
    )
    assert cur.lastrowid is not None, "INSERT returned no lastrowid"
    return int(cur.lastrowid)


def _insert_embedding(
    conn: sqlite3.Connection,
    ad_id: int,
    vec: np.ndarray[tuple[int], np.dtype[np.float32]],
) -> None:
    blob = embedding_to_blob(vec)
    _ = conn.execute(
        "INSERT INTO voice_embeddings (ad_id, speaker, embedding) VALUES (?, '', ?)",
        (ad_id, blob),
    )


def _insert_llm(
    conn: sqlite3.Connection,
    ad_id: int,
    ad_type: str | None,
    tone: str | None,
) -> None:
    sql = (
        "INSERT INTO llm_analyses (ad_id, ad_type, tone, raw_response)"
        " VALUES (?, ?, ?, '{}')"
    )
    _ = conn.execute(sql, (ad_id, ad_type, tone))


# ---------------------------------------------------------------------------
# hourly_frequency
# ---------------------------------------------------------------------------


def test_hourly_frequency_empty(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    with db.connect(db_path) as conn:
        result = hourly_frequency(conn)
    assert result == []


def test_hourly_frequency_counts_by_hour(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    with db.connect(db_path) as conn:
        _ = _insert_done_ad(conn, "a.wav", "2026-01-01T08:00:00Z")
        _ = _insert_done_ad(conn, "b.wav", "2026-01-01T08:30:00Z")
        _ = _insert_done_ad(conn, "c.wav", "2026-01-01T14:00:00Z")

    with db.connect(db_path) as conn:
        result = hourly_frequency(conn)

    assert len(result) == 2
    assert result[0]["hour"] == 8
    assert result[0]["count"] == 2
    assert result[1]["hour"] == 14
    assert result[1]["count"] == 1


def test_hourly_frequency_excludes_non_done(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    _error_sql = (
        "INSERT INTO ads (filename, recorded_at, status)"
        " VALUES ('e.wav', '2026-01-01T09:00:00Z', 'error')"
    )
    with db.connect(db_path) as conn:
        _ = conn.execute(_error_sql)
        _ = _insert_done_ad(conn, "f.wav", "2026-01-01T09:30:00Z")

    with db.connect(db_path) as conn:
        result = hourly_frequency(conn)

    assert len(result) == 1
    assert result[0]["count"] == 1


def test_hourly_frequency_ordered(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    with db.connect(db_path) as conn:
        _ = _insert_done_ad(conn, "z.wav", "2026-01-01T23:00:00Z")
        _ = _insert_done_ad(conn, "a.wav", "2026-01-01T00:00:00Z")

    with db.connect(db_path) as conn:
        result = hourly_frequency(conn)

    assert result[0]["hour"] == 0
    assert result[-1]["hour"] == 23


# ---------------------------------------------------------------------------
# ad_type_distribution
# ---------------------------------------------------------------------------


def test_ad_type_distribution_empty(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    with db.connect(db_path) as conn:
        result = ad_type_distribution(conn)
    assert result == []


def test_ad_type_distribution_counts_and_percentage(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    with db.connect(db_path) as conn:
        id1 = _insert_done_ad(conn, "a.wav")
        id2 = _insert_done_ad(conn, "b.wav")
        id3 = _insert_done_ad(conn, "c.wav")
        _insert_llm(conn, id1, "brand", None)
        _insert_llm(conn, id2, "brand", None)
        _insert_llm(conn, id3, "promo", None)

    with db.connect(db_path) as conn:
        result = ad_type_distribution(conn)

    assert result[0]["ad_type"] == "brand"
    assert result[0]["count"] == 2
    assert abs(result[0]["percentage"] - 66.67) < 0.01
    assert result[1]["ad_type"] == "promo"
    assert result[1]["count"] == 1
    assert abs(result[1]["percentage"] - 33.33) < 0.01


def test_ad_type_distribution_null_ad_type(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    with db.connect(db_path) as conn:
        id1 = _insert_done_ad(conn, "a.wav")
        _insert_llm(conn, id1, None, None)

    with db.connect(db_path) as conn:
        result = ad_type_distribution(conn)

    assert result[0]["ad_type"] is None
    assert result[0]["count"] == 1
    assert result[0]["percentage"] == 100.0


# ---------------------------------------------------------------------------
# tone_distribution
# ---------------------------------------------------------------------------


def test_tone_distribution_empty(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    with db.connect(db_path) as conn:
        result = tone_distribution(conn)
    assert result == []


def test_tone_distribution_counts(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    with db.connect(db_path) as conn:
        id1 = _insert_done_ad(conn, "a.wav")
        id2 = _insert_done_ad(conn, "b.wav")
        id3 = _insert_done_ad(conn, "c.wav")
        _insert_llm(conn, id1, None, "friendly")
        _insert_llm(conn, id2, None, "friendly")
        _insert_llm(conn, id3, None, "serious")

    with db.connect(db_path) as conn:
        result = tone_distribution(conn)

    assert result[0]["tone"] == "friendly"
    assert result[0]["count"] == 2
    assert result[1]["tone"] == "serious"
    assert result[1]["count"] == 1


# ---------------------------------------------------------------------------
# detect_repeat_ads
# ---------------------------------------------------------------------------


def _unit_vec(idx: int) -> np.ndarray[tuple[int], np.dtype[np.float32]]:
    """Return a 256-dim float32 unit vector (1 at *idx*, 0 elsewhere)."""
    v = np.zeros(256, dtype=np.float32)
    v[idx % 256] = 1.0
    return v


def test_detect_repeat_ads_empty(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    with db.connect(db_path) as conn:
        result = detect_repeat_ads(conn)
    assert result == []


def test_detect_repeat_ads_single_ad(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    with db.connect(db_path) as conn:
        id1 = _insert_done_ad(conn, "a.wav")
        _insert_embedding(conn, id1, _unit_vec(0))

    with db.connect(db_path) as conn:
        result = detect_repeat_ads(conn)
    assert result == []


def test_detect_repeat_ads_identical_embeddings(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    vec = _unit_vec(0)
    with db.connect(db_path) as conn:
        id1 = _insert_done_ad(conn, "a.wav")
        id2 = _insert_done_ad(conn, "b.wav")
        _insert_embedding(conn, id1, vec)
        _insert_embedding(conn, id2, vec.copy())

    with db.connect(db_path) as conn:
        result = detect_repeat_ads(conn, threshold=0.90)

    assert len(result) == 1
    assert result[0]["ad_id_a"] == id1
    assert result[0]["ad_id_b"] == id2
    assert abs(result[0]["similarity"] - 1.0) < 1e-5


def test_detect_repeat_ads_orthogonal_not_matched(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    with db.connect(db_path) as conn:
        id1 = _insert_done_ad(conn, "a.wav")
        id2 = _insert_done_ad(conn, "b.wav")
        _insert_embedding(conn, id1, _unit_vec(0))
        _insert_embedding(conn, id2, _unit_vec(1))

    with db.connect(db_path) as conn:
        result = detect_repeat_ads(conn, threshold=0.90)
    assert result == []


def test_detect_repeat_ads_sorted_by_similarity_desc(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    v0 = _unit_vec(0)
    # High similarity: angle ~11°
    v1 = np.zeros(256, dtype=np.float32)
    v1[0] = np.cos(np.radians(11.0))
    v1[1] = np.sin(np.radians(11.0))
    # Lower (but still ≥ 0.90): angle ~26°
    v2 = np.zeros(256, dtype=np.float32)
    v2[0] = np.cos(np.radians(26.0))
    v2[1] = np.sin(np.radians(26.0))
    with db.connect(db_path) as conn:
        id1 = _insert_done_ad(conn, "a.wav")
        id2 = _insert_done_ad(conn, "b.wav")
        id3 = _insert_done_ad(conn, "c.wav")
        _insert_embedding(conn, id1, v0)
        _insert_embedding(conn, id2, v1)
        _insert_embedding(conn, id3, v2)

    with db.connect(db_path) as conn:
        result = detect_repeat_ads(conn, threshold=0.89)

    assert len(result) >= 2
    for i in range(len(result) - 1):
        assert result[i]["similarity"] >= result[i + 1]["similarity"]


def test_detect_repeat_ads_excludes_non_done(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    vec = _unit_vec(0)
    with db.connect(db_path) as conn:
        id1 = _insert_done_ad(conn, "a.wav")
        _error_sql = (
            "INSERT INTO ads (filename, recorded_at, status)"
            " VALUES ('b.wav', '2026-01-01T12:00:00Z', 'error')"
        )
        _ = conn.execute(_error_sql)
        id2 = int(
            conn.execute("SELECT id FROM ads WHERE filename='b.wav'").fetchone()["id"]
        )
        _insert_embedding(conn, id1, vec)
        _insert_embedding(conn, id2, vec.copy())

    with db.connect(db_path) as conn:
        result = detect_repeat_ads(conn, threshold=0.90)
    assert result == []


def test_detect_repeat_ads_returns_repeat_ad_pair_row_fields(
    tmp_path: Path,
) -> None:
    db_path = _make_db(tmp_path)
    vec = _unit_vec(0)
    with db.connect(db_path) as conn:
        id1 = _insert_done_ad(conn, "x.wav")
        id2 = _insert_done_ad(conn, "y.wav")
        _insert_embedding(conn, id1, vec)
        _insert_embedding(conn, id2, vec.copy())

    with db.connect(db_path) as conn:
        result = detect_repeat_ads(conn, threshold=0.90)

    row = result[0]
    assert row["filename_a"] == "x.wav"
    assert row["filename_b"] == "y.wav"
    assert isinstance(row["similarity"], float)


# ---------------------------------------------------------------------------
# PatternReport
# ---------------------------------------------------------------------------


def test_pattern_report_to_dict(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    r = report(db_path)
    d = r.to_dict()
    assert set(d.keys()) == {
        "hourly_frequency",
        "ad_type_distribution",
        "tone_distribution",
        "repeat_ad_pairs",
    }
    assert isinstance(d["hourly_frequency"], list)


def test_report_returns_pattern_report(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    r = report(db_path)
    assert isinstance(r, PatternReport)


def test_report_custom_threshold(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    # threshold kwarg is accepted without error
    r = report(db_path, threshold=0.95)
    assert isinstance(r, PatternReport)


# ---------------------------------------------------------------------------
# threshold validation
# ---------------------------------------------------------------------------


def test_detect_repeat_ads_invalid_threshold_above(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    with (
        db.connect(db_path) as conn,
        pytest.raises(ValueError, match="threshold must be in"),
    ):
        _ = detect_repeat_ads(conn, threshold=1.1)


def test_detect_repeat_ads_invalid_threshold_below(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    with (
        db.connect(db_path) as conn,
        pytest.raises(ValueError, match="threshold must be in"),
    ):
        _ = detect_repeat_ads(conn, threshold=-0.1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_main_report_outputs_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = _make_db(tmp_path)
    main(["report", "--db", str(db_path)])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert set(data.keys()) == {
        "hourly_frequency",
        "ad_type_distribution",
        "tone_distribution",
        "repeat_ad_pairs",
    }


def test_main_report_invalid_threshold_exits(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    with pytest.raises(SystemExit):
        main(["report", "--db", str(db_path), "--threshold", "2.0"])
