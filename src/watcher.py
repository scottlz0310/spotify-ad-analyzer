from __future__ import annotations

import logging
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast, override

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from src import config
from src.pipeline import run_pipeline

if TYPE_CHECKING:
    from watchdog.events import FileSystemEvent

_logger = logging.getLogger(__name__)

_AD_GLOB = "spotify_ad_*.wav"
_MAX_SEEN = 256


class ObserverProtocol(Protocol):
    """Minimal interface required from a watchdog observer."""

    def stop(self) -> None: ...
    def join(self, timeout: float | None = None) -> None: ...


def is_ad_file(path: str | Path) -> bool:
    """Return True if *path* matches the Spotify ad filename pattern."""
    return Path(path).match(_AD_GLOB)


class AdFileHandler(FileSystemEventHandler):
    """Watchdog event handler that runs the analysis pipeline on new ad files.

    ``on_closed`` is triggered by Linux inotify ``IN_CLOSE_WRITE``, meaning the
    file is fully written before the pipeline processes it.
    """

    def __init__(self, db_path: Path) -> None:
        super().__init__()
        self._db_path: Path = db_path
        self._seen: OrderedDict[str, None] = OrderedDict()

    @override
    def on_closed(self, event: FileSystemEvent) -> None:
        """Process a file once it is fully written (Linux inotify IN_CLOSE_WRITE)."""
        if event.is_directory:
            return
        src_path = str(event.src_path)
        if not is_ad_file(src_path):
            return
        if src_path in self._seen:
            _logger.debug("Skipping already-processed file: %s", src_path)
            return
        # Add before pipeline to prevent duplicate concurrent processing.
        # Evict the oldest entry once the cap is exceeded.
        self._seen[src_path] = None
        if len(self._seen) > _MAX_SEEN:
            _ = self._seen.popitem(last=False)
        audio_path = Path(src_path)
        _logger.info("New ad file detected: %s", audio_path.name)
        try:
            result = run_pipeline(audio_path, self._db_path)
            _logger.info(
                "Pipeline complete: ad_id=%d %s", result.ad_id, audio_path.name
            )
        except Exception:
            # Remove from seen so the file can be retried on a subsequent event.
            self._seen.pop(src_path, None)
            _logger.exception("Pipeline failed for %s", audio_path.name)


def start_watcher(
    *,
    watch_dir: Path | None = None,
    db_path: Path | None = None,
) -> ObserverProtocol:
    """Create and start a watchdog observer for the shared directory.

    Parameters
    ----------
    watch_dir:
        Directory to watch.  Defaults to ``config.SHARED_DIR``.
    db_path:
        SQLite database path.  Defaults to ``config.DATA_DIR / "ads.db"``.

    Returns
    -------
    ObserverProtocol
        Running observer instance.  Call ``.stop()`` then ``.join()`` to
        shut down cleanly.
    """
    if watch_dir is None:
        watch_dir = config.SHARED_DIR
    if db_path is None:
        db_path = config.DATA_DIR / "ads.db"

    watch_dir.mkdir(parents=True, exist_ok=True)

    handler = AdFileHandler(db_path)
    observer = Observer()
    _ = observer.schedule(handler, str(watch_dir), recursive=False)
    observer.start()
    _logger.info("Watching %s for %s", watch_dir, _AD_GLOB)
    return cast("ObserverProtocol", observer)
