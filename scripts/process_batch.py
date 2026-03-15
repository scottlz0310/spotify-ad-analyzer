"""Batch-process WAV files from a directory through the full pipeline.

Usage (inside container):
    python scripts/process_batch.py /app/dropbox_shared /app/data/dropbox_ads.db
"""

from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path

from src import db
from src.pipeline import run_pipeline
from src.splitter import split_if_needed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
_logger = logging.getLogger("batch")


def main(input_dir: Path, db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db.init_db(db_path)
    wav_files = sorted(input_dir.glob("spotify_ad_*.wav"))
    _logger.info("Found %d WAV files in %s", len(wav_files), input_dir)

    total_parts = 0
    with tempfile.TemporaryDirectory() as tmp:
        split_dir = Path(tmp) / "split"
        split_dir.mkdir()

        for wav in wav_files:
            parts = split_if_needed(wav, output_dir=split_dir)
            _logger.info(
                "%s  ->  %d part(s): %s",
                wav.name,
                len(parts),
                [p.name for p in parts],
            )
            for part in parts:
                try:
                    result = run_pipeline(part, db_path)
                    _logger.info("  [OK] ad_id=%d  %s", result.ad_id, part.name)
                    total_parts += 1
                except Exception:
                    _logger.exception("  [FAIL] %s", part.name)
                finally:
                    if part != wav:
                        part.unlink(missing_ok=True)

    _logger.info("Done. Processed %d parts total -> %s", total_parts, db_path)


if __name__ == "__main__":
    if len(sys.argv) != 3:  # noqa: PLR2004
        print(f"Usage: {sys.argv[0]} <input_dir> <db_path>", file=sys.stderr)  # noqa: T201
        sys.exit(1)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
