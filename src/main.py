from __future__ import annotations

import logging
import signal
import sys
import threading
from typing import TYPE_CHECKING

from src import config, db
from src.watcher import start_watcher

if TYPE_CHECKING:
    from types import FrameType

_logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    """Configure root logger to write INFO+ messages to stdout."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        stream=sys.stdout,
        force=True,
    )


def main() -> None:
    """Start the ad analyzer: watch SHARED_DIR and run the pipeline on new ad WAVs."""
    _setup_logging()
    _logger.info("spotify-ad-analyzer starting")

    db_path = config.DATA_DIR / "ads.db"
    db.init_db(db_path)

    stop_event = threading.Event()

    def _shutdown(signum: int, _frame: FrameType | None) -> None:
        _logger.info("Received signal %d, shutting down…", signum)
        stop_event.set()

    for _sig in (signal.SIGINT, signal.SIGTERM):
        _ = signal.signal(_sig, _shutdown)

    observer = start_watcher(db_path=db_path)
    _logger.info("Watching %s — press Ctrl-C to stop", config.SHARED_DIR)

    try:
        _ = stop_event.wait()
    finally:
        observer.stop()
        observer.join()
        _logger.info("spotify-ad-analyzer stopped")


if __name__ == "__main__":
    main()
