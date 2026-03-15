#!/usr/bin/env python3
"""Backfill LLM analysis for ads that have transcripts but no llm_analyses row.

Usage (inside the analyzer Docker container):
    python scripts/backfill_llm.py [--limit N] [--dry-run]

Or via docker compose:
    docker compose run --rm analyzer python scripts/backfill_llm.py
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from src import config, db
from src.llm_analyzer import OllamaError, analyze_transcript

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    stream=sys.stdout,
)
_logger = logging.getLogger("backfill_llm")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill LLM analysis for existing ads"
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="Max ads to process (0=all)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without calling LLM",
    )
    args = parser.parse_args()

    db_path = config.DATA_DIR / "ads.db"
    db.init_db(db_path)

    with db.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT t.ad_id, t.full_text
            FROM transcripts t
            LEFT JOIN llm_analyses l ON t.ad_id = l.ad_id
            WHERE l.ad_id IS NULL
              AND t.full_text IS NOT NULL
              AND t.full_text != ''
            ORDER BY t.ad_id
            """
        ).fetchall()

        total = len(rows)
        if args.limit:
            rows = rows[: args.limit]

        _logger.info(
            "Found %d ads without LLM analysis (processing %d, model=%s)",
            total,
            len(rows),
            config.OLLAMA_MODEL,
        )

        if args.dry_run:
            for row in rows:
                _logger.info("  [dry-run] ad_id=%d text_len=%d", row[0], len(row[1]))
            return

        success = 0
        errors = 0
        for i, (ad_id, transcript) in enumerate(rows, 1):
            _logger.info("[%d/%d] Analyzing ad_id=%d ...", i, len(rows), ad_id)
            try:
                result = analyze_transcript(transcript)
                db.upsert_llm_analysis(
                    conn,
                    ad_id=ad_id,
                    raw_response=result.raw_response,
                    product_name=result.product_name,
                    ad_type=result.ad_type,
                    summary=result.summary,
                    tone=result.tone,
                )
                conn.commit()
                _logger.info(
                    "  → product=%r type=%r tone=%r",
                    result.product_name,
                    result.ad_type,
                    result.tone,
                )
                success += 1
            except OllamaError:
                _logger.exception("  ✗ OllamaError for ad_id=%d", ad_id)
                errors += 1
                time.sleep(2)
            except Exception:
                _logger.exception("  ✗ Unexpected error for ad_id=%d", ad_id)
                errors += 1

        _logger.info(
            "Done: %d succeeded, %d errors out of %d total", success, errors, len(rows)
        )


if __name__ == "__main__":
    main()
