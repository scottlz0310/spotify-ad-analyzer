"""Pattern analysis: SQL-based aggregate reports from ads.db.

Public API
----------
hourly_frequency(conn)
    Count of *done* ads per hour-of-day (0-23).

ad_type_distribution(conn)
    Count + percentage of ads per LLM-detected ``ad_type``.

tone_distribution(conn)
    Count + percentage of ads per LLM-detected ``tone``.

detect_repeat_ads(conn, threshold)
    Pairs of ads whose voice embeddings exceed *threshold* cosine similarity.

report(db_path, threshold)
    Convenience wrapper that opens the DB and returns a ``PatternReport``.

CLI
---
``python -m src.pattern_analyzer report [--db PATH] [--threshold FLOAT]``
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict, final

import numpy as np

from src import db as _db
from src.embedder import blob_to_embedding

if TYPE_CHECKING:
    import sqlite3


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class HourlyFrequencyRow(TypedDict):
    hour: int
    count: int


class AdTypeDistributionRow(TypedDict):
    ad_type: str | None
    count: int
    percentage: float


class ToneDistributionRow(TypedDict):
    tone: str | None
    count: int
    percentage: float


class RepeatAdPairRow(TypedDict):
    ad_id_a: int
    filename_a: str
    ad_id_b: int
    filename_b: str
    similarity: float


@final
class PatternReport:
    """Container for all pattern-analysis results."""

    __slots__ = (
        "ad_type_distribution",
        "hourly_frequency",
        "repeat_ad_pairs",
        "tone_distribution",
    )

    def __init__(
        self,
        hourly_frequency: list[HourlyFrequencyRow],
        ad_type_distribution: list[AdTypeDistributionRow],
        tone_distribution: list[ToneDistributionRow],
        repeat_ad_pairs: list[RepeatAdPairRow],
    ) -> None:
        self.hourly_frequency = hourly_frequency
        self.ad_type_distribution = ad_type_distribution
        self.tone_distribution = tone_distribution
        self.repeat_ad_pairs = repeat_ad_pairs

    def to_dict(self) -> dict[str, object]:
        return {
            "hourly_frequency": list(self.hourly_frequency),
            "ad_type_distribution": list(self.ad_type_distribution),
            "tone_distribution": list(self.tone_distribution),
            "repeat_ad_pairs": list(self.repeat_ad_pairs),
        }


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


def hourly_frequency(conn: sqlite3.Connection) -> list[HourlyFrequencyRow]:
    """Return per-hour ad counts for *done* ads, ordered ascending by hour.

    Only hours that have at least one *done* ad are included; hours with zero
    ads are omitted.
    """
    sql = """
        SELECT
            CAST(strftime('%H', recorded_at) AS INTEGER) AS hour,
            COUNT(*) AS count
        FROM ads
        WHERE status = 'done'
        GROUP BY hour
        ORDER BY hour
    """
    rows = conn.execute(sql).fetchall()
    return [
        HourlyFrequencyRow(hour=int(r["hour"]), count=int(r["count"])) for r in rows
    ]


def ad_type_distribution(conn: sqlite3.Connection) -> list[AdTypeDistributionRow]:
    """Return per-ad_type counts + percentage for ads with LLM analysis."""
    sql = """
        SELECT
            la.ad_type,
            COUNT(*) AS count,
            ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS percentage
        FROM llm_analyses la
        JOIN ads a ON a.id = la.ad_id
        WHERE a.status = 'done'
        GROUP BY la.ad_type
        ORDER BY count DESC
    """
    rows = conn.execute(sql).fetchall()
    return [
        AdTypeDistributionRow(
            ad_type=r["ad_type"],
            count=int(r["count"]),
            percentage=float(r["percentage"]),
        )
        for r in rows
    ]


def tone_distribution(conn: sqlite3.Connection) -> list[ToneDistributionRow]:
    """Return per-tone counts + percentage for ads with LLM analysis."""
    sql = """
        SELECT
            la.tone,
            COUNT(*) AS count,
            ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS percentage
        FROM llm_analyses la
        JOIN ads a ON a.id = la.ad_id
        WHERE a.status = 'done'
        GROUP BY la.tone
        ORDER BY count DESC
    """
    rows = conn.execute(sql).fetchall()
    return [
        ToneDistributionRow(
            tone=r["tone"],
            count=int(r["count"]),
            percentage=float(r["percentage"]),
        )
        for r in rows
    ]


def detect_repeat_ads(
    conn: sqlite3.Connection,
    threshold: float = 0.90,
) -> list[RepeatAdPairRow]:
    """Return pairs of ads whose voice embeddings exceed *threshold* cosine similarity.

    Embeddings are loaded from SQLite and cosine similarity is computed in
    Python via numpy.  Only ``done`` ads with an embedding (``speaker=""``)
    are considered.  Each pair is returned once (a.id < b.id).

    Args:
        conn: Open SQLite connection.
        threshold: Cosine-similarity inclusion threshold; must be in [0.0, 1.0].

    Raises:
        ValueError: If *threshold* is outside [0.0, 1.0].

    Note:
        This builds a full N x N similarity matrix (O(N**2) memory).  For very
        large databases consider chunking or incremental row-wise dot products.
    """
    if not (0.0 <= threshold <= 1.0):
        msg = f"threshold must be in [0.0, 1.0], got {threshold!r}"
        raise ValueError(msg)
    sql = """
        SELECT ve.ad_id, a.filename, ve.embedding
        FROM voice_embeddings ve
        JOIN ads a ON a.id = ve.ad_id
        WHERE ve.speaker = '' AND a.status = 'done'
        ORDER BY ve.ad_id
    """
    rows = conn.execute(sql).fetchall()
    _min_pairs = 2
    if len(rows) < _min_pairs:
        return []

    ids: list[int] = [int(r["ad_id"]) for r in rows]
    filenames: list[str] = [str(r["filename"]) for r in rows]
    embeddings: list[np.ndarray[tuple[int], np.dtype[np.float32]]] = [
        blob_to_embedding(bytes(r["embedding"])) for r in rows
    ]

    # Stack into matrix and L2-normalise rows for fast cosine similarity
    mat = np.stack(embeddings).astype(np.float32)
    norms = np.linalg.norm(mat, axis=1, keepdims=True).astype(np.float32)
    norms = np.where(norms == 0, np.float32(1.0), norms)
    mat = mat / norms
    # Pairwise cosine similarity matrix
    sim_matrix = (mat @ mat.T).astype(np.float32)

    pairs: list[RepeatAdPairRow] = []
    n = len(ids)
    for i in range(n):
        for j in range(i + 1, n):
            sim = float(sim_matrix[i, j])
            if sim >= threshold:
                pairs.append(
                    RepeatAdPairRow(
                        ad_id_a=ids[i],
                        filename_a=filenames[i],
                        ad_id_b=ids[j],
                        filename_b=filenames[j],
                        similarity=sim,
                    )
                )
    return sorted(pairs, key=lambda p: p["similarity"], reverse=True)


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------


def report(db_path: Path, threshold: float = 0.90) -> PatternReport:
    """Open *db_path* and return a full :class:`PatternReport`."""
    with _db.connect(db_path) as conn:
        return PatternReport(
            hourly_frequency=hourly_frequency(conn),
            ad_type_distribution=ad_type_distribution(conn),
            tone_distribution=tone_distribution(conn),
            repeat_ad_pairs=detect_repeat_ads(conn, threshold=threshold),
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _threshold_type(value: str) -> float:
    """Argparse type for cosine-similarity threshold; enforces [0.0, 1.0]."""
    f = float(value)
    if not (0.0 <= f <= 1.0):
        msg = f"threshold must be in [0.0, 1.0], got {value!r}"
        raise argparse.ArgumentTypeError(msg)
    return f


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.pattern_analyzer",
        description="Generate a pattern-analysis report from ads.db.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    rep = sub.add_parser("report", help="Print a JSON pattern report.")
    _ = rep.add_argument(
        "--db",
        metavar="PATH",
        default="data/ads.db",
        help="Path to the SQLite database (default: data/ads.db).",
    )
    _ = rep.add_argument(
        "--threshold",
        metavar="FLOAT",
        type=_threshold_type,
        default=0.90,
        help="Cosine-similarity threshold for repeat-ad detection (default: 0.90).",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    if args.command == "report":
        result = report(Path(args.db), threshold=args.threshold)
        json.dump(result.to_dict(), sys.stdout, ensure_ascii=False, indent=2)
        _ = sys.stdout.write("\n")


if __name__ == "__main__":
    main()  # pragma: no cover
