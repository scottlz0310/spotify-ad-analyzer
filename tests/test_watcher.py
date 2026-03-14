from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from watchdog.events import FileClosedEvent

from src.watcher import AdFileHandler, is_ad_file, start_watcher

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_closed_event(src_path: str) -> FileClosedEvent:
    return FileClosedEvent(src_path=src_path)


# ---------------------------------------------------------------------------
# is_ad_file
# ---------------------------------------------------------------------------


class TestIsAdFile:
    def test_bare_matching_filename(self) -> None:
        assert is_ad_file("spotify_ad_2026-01-01T00-00-00.wav")

    def test_full_path_matching(self) -> None:
        assert is_ad_file("/app/shared/spotify_ad_2026-01-01T00-00-00.wav")

    def test_non_matching_filename(self) -> None:
        assert not is_ad_file("music_track.wav")

    def test_wrong_prefix(self) -> None:
        assert not is_ad_file("ad_2026-01-01T00-00-00.wav")

    def test_wrong_extension(self) -> None:
        assert not is_ad_file("spotify_ad_2026-01-01T00-00-00.mp3")

    def test_accepts_path_object(self) -> None:
        assert is_ad_file(Path("/shared/spotify_ad_test.wav"))


# ---------------------------------------------------------------------------
# AdFileHandler.on_closed
# ---------------------------------------------------------------------------


class TestAdFileHandler:
    def _make_handler(self, tmp_path: Path) -> AdFileHandler:
        return AdFileHandler(db_path=tmp_path / "ads.db")

    def test_on_closed_calls_pipeline_for_ad_file(self, tmp_path: Path) -> None:
        handler = self._make_handler(tmp_path)
        event = _make_closed_event("/shared/spotify_ad_2026-01-01.wav")

        with patch("src.watcher.run_pipeline") as mock_pipeline:
            mock_pipeline.return_value = MagicMock(ad_id=1)
            handler.on_closed(event)

        mock_pipeline.assert_called_once()

    def test_on_closed_passes_correct_args(self, tmp_path: Path) -> None:
        db_path = tmp_path / "ads.db"
        handler = AdFileHandler(db_path=db_path)
        audio = "/shared/spotify_ad_2026-01-01.wav"
        event = _make_closed_event(audio)

        with patch("src.watcher.run_pipeline") as mock_pipeline:
            mock_pipeline.return_value = MagicMock(ad_id=1)
            handler.on_closed(event)

        mock_pipeline.assert_called_once_with(Path(audio), db_path)

    def test_on_closed_skips_non_ad_file(self, tmp_path: Path) -> None:
        handler = self._make_handler(tmp_path)
        event = _make_closed_event("/shared/music_track.wav")

        with patch("src.watcher.run_pipeline") as mock_pipeline:
            handler.on_closed(event)

        mock_pipeline.assert_not_called()

    def test_on_closed_skips_directory_event(self, tmp_path: Path) -> None:
        handler = self._make_handler(tmp_path)
        event = MagicMock()
        event.is_directory = True
        event.src_path = "/shared/spotify_ad_2026-01-01.wav"

        with patch("src.watcher.run_pipeline") as mock_pipeline:
            handler.on_closed(event)

        mock_pipeline.assert_not_called()

    def test_on_closed_deduplicates_same_path(self, tmp_path: Path) -> None:
        handler = self._make_handler(tmp_path)
        event = _make_closed_event("/shared/spotify_ad_2026-01-01.wav")

        with patch("src.watcher.run_pipeline") as mock_pipeline:
            mock_pipeline.return_value = MagicMock(ad_id=1)
            handler.on_closed(event)
            handler.on_closed(event)

        mock_pipeline.assert_called_once()

    def test_on_closed_processes_distinct_files_independently(
        self, tmp_path: Path
    ) -> None:
        handler = self._make_handler(tmp_path)
        event_a = _make_closed_event("/shared/spotify_ad_001.wav")
        event_b = _make_closed_event("/shared/spotify_ad_002.wav")

        with patch("src.watcher.run_pipeline") as mock_pipeline:
            mock_pipeline.return_value = MagicMock(ad_id=1)
            handler.on_closed(event_a)
            handler.on_closed(event_b)

        assert mock_pipeline.call_count == 2

    def test_on_closed_pipeline_error_does_not_raise(self, tmp_path: Path) -> None:
        handler = self._make_handler(tmp_path)
        event = _make_closed_event("/shared/spotify_ad_2026-01-01.wav")

        with patch("src.watcher.run_pipeline") as mock_pipeline:
            mock_pipeline.side_effect = RuntimeError("pipeline failed")
            handler.on_closed(event)  # must not propagate


# ---------------------------------------------------------------------------
# start_watcher
# ---------------------------------------------------------------------------


class TestStartWatcher:
    def test_returns_started_observer(self, tmp_path: Path) -> None:
        with patch("src.watcher.Observer") as mock_cls:
            mock_obs = MagicMock()
            mock_cls.return_value = mock_obs

            result = start_watcher(watch_dir=tmp_path, db_path=tmp_path / "ads.db")

        assert result is mock_obs
        mock_obs.start.assert_called_once()

    def test_schedules_handler_on_watch_dir(self, tmp_path: Path) -> None:
        with patch("src.watcher.Observer") as mock_cls:
            mock_obs = MagicMock()
            mock_cls.return_value = mock_obs

            _ = start_watcher(watch_dir=tmp_path, db_path=tmp_path / "ads.db")

        mock_obs.schedule.assert_called_once()
        _args, kwargs = mock_obs.schedule.call_args
        assert kwargs.get("recursive") is False or _args[-1] is False

    def test_creates_watch_dir_if_missing(self, tmp_path: Path) -> None:
        watch_dir = tmp_path / "new_shared"
        with patch("src.watcher.Observer"):
            _ = start_watcher(watch_dir=watch_dir, db_path=tmp_path / "ads.db")

        assert watch_dir.is_dir()

    def test_default_watch_dir_from_config(self, tmp_path: Path) -> None:
        with (
            patch("src.watcher.Observer") as mock_cls,
            patch("src.watcher.config") as mock_config,
        ):
            mock_config.SHARED_DIR = tmp_path / "shared"
            mock_config.DATA_DIR = tmp_path / "data"
            mock_obs = MagicMock()
            mock_cls.return_value = mock_obs

            _ = start_watcher()

        mock_obs.start.assert_called_once()
        assert (tmp_path / "shared").is_dir()
