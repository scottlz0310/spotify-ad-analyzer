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
        assert is_ad_file("spotify_ad_2026-01-01_00-00-00.wav")

    def test_full_path_matching(self) -> None:
        assert is_ad_file("/app/shared/spotify_ad_2026-01-01_00-00-00.wav")

    def test_non_matching_filename(self) -> None:
        assert not is_ad_file("music_track.wav")

    def test_wrong_prefix(self) -> None:
        assert not is_ad_file("ad_2026-01-01_00-00-00.wav")

    def test_wrong_extension(self) -> None:
        assert not is_ad_file("spotify_ad_2026-01-01_00-00-00.mp3")

    def test_accepts_path_object(self) -> None:
        assert is_ad_file(Path("/shared/spotify_ad_test.wav"))


# ---------------------------------------------------------------------------
# AdFileHandler.on_closed
# ---------------------------------------------------------------------------


class TestAdFileHandler:
    def _make_handler(self, tmp_path: Path, *, polling: bool = False) -> AdFileHandler:
        # Inject a no-op splitter so tests do not require real WAV files on disk.
        return AdFileHandler(
            db_path=tmp_path / "ads.db",
            polling=polling,
            split_fn=lambda p: [p],
        )

    def test_on_closed_calls_pipeline_for_ad_file(self, tmp_path: Path) -> None:
        handler = self._make_handler(tmp_path)
        event = _make_closed_event("/shared/spotify_ad_2026-01-01_00-00-00.wav")

        with patch("src.watcher.run_pipeline") as mock_pipeline:
            mock_pipeline.return_value = MagicMock(ad_id=1)
            handler.on_closed(event)

        mock_pipeline.assert_called_once()

    def test_on_closed_passes_correct_args(self, tmp_path: Path) -> None:
        db_path = tmp_path / "ads.db"
        audio = "/shared/spotify_ad_2026-01-01_00-00-00.wav"
        handler = AdFileHandler(db_path=db_path, split_fn=lambda p: [p])
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
        event.src_path = "/shared/spotify_ad_2026-01-01_00-00-00.wav"

        with patch("src.watcher.run_pipeline") as mock_pipeline:
            handler.on_closed(event)

        mock_pipeline.assert_not_called()

    def test_on_closed_deduplicates_same_path(self, tmp_path: Path) -> None:
        handler = self._make_handler(tmp_path)
        event = _make_closed_event("/shared/spotify_ad_2026-01-01_00-00-00.wav")

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
        event = _make_closed_event("/shared/spotify_ad_2026-01-01_00-00-00.wav")

        with patch("src.watcher.run_pipeline") as mock_pipeline:
            mock_pipeline.side_effect = RuntimeError("pipeline failed")
            handler.on_closed(event)  # must not propagate

    def test_on_closed_pipeline_error_allows_retry(self, tmp_path: Path) -> None:
        """After pipeline failure the file is removed from _seen — retry is possible."""
        handler = self._make_handler(tmp_path)
        event = _make_closed_event("/shared/spotify_ad_2026-01-01_00-00-00.wav")

        with patch("src.watcher.run_pipeline") as mock_pipeline:
            mock_pipeline.side_effect = RuntimeError("transient error")
            handler.on_closed(event)

        # Access via the public name to satisfy the linter
        seen: dict[str, None] = handler._seen  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert str(event.src_path) not in seen

    def test_on_closed_non_runtime_error_does_not_raise(self, tmp_path: Path) -> None:
        """Non-RuntimeError exceptions (e.g. OSError) must also be caught."""
        handler = self._make_handler(tmp_path)
        event = _make_closed_event("/shared/spotify_ad_2026-01-01_00-00-00.wav")

        with patch("src.watcher.run_pipeline") as mock_pipeline:
            mock_pipeline.side_effect = OSError("file gone")
            handler.on_closed(event)  # must not propagate

    def test_on_created_ignored_in_inotify_mode(self, tmp_path: Path) -> None:
        """on_created must be a no-op when polling=False (inotify Observer mode)."""
        handler = self._make_handler(tmp_path, polling=False)
        event = _make_closed_event("/shared/spotify_ad_2026-01-01_00-00-00.wav")

        with patch("src.watcher.run_pipeline") as mock_pipeline:
            handler.on_created(event)

        mock_pipeline.assert_not_called()

    def test_on_created_triggers_pipeline_in_polling_mode(self, tmp_path: Path) -> None:
        """on_created must trigger the pipeline when polling=True."""
        handler = self._make_handler(tmp_path, polling=True)
        event = _make_closed_event("/shared/spotify_ad_2026-01-01_00-00-00.wav")

        with patch("src.watcher.run_pipeline") as mock_pipeline:
            mock_pipeline.return_value = MagicMock(ad_id=1)
            handler.on_created(event)

        mock_pipeline.assert_called_once()

    def test_on_closed_ignored_in_polling_mode(self, tmp_path: Path) -> None:
        """on_closed must be a no-op when polling=True (PollingObserver mode)."""
        handler = self._make_handler(tmp_path, polling=True)
        event = _make_closed_event("/shared/spotify_ad_2026-01-01_00-00-00.wav")

        with patch("src.watcher.run_pipeline") as mock_pipeline:
            handler.on_closed(event)

        mock_pipeline.assert_not_called()

    def test_split_fn_called_for_each_ad_file(self, tmp_path: Path) -> None:
        """split_fn is invoked once per detected ad file."""
        splits: list[Path] = []

        def tracking_split(p: Path) -> list[Path]:
            splits.append(p)
            return [p]

        handler = AdFileHandler(
            db_path=tmp_path / "ads.db",
            split_fn=tracking_split,
        )
        event = _make_closed_event("/shared/spotify_ad_2026-01-01_00-00-00.wav")
        with patch("src.watcher.run_pipeline") as mock_pipeline:
            mock_pipeline.return_value = MagicMock(ad_id=1)
            handler.on_closed(event)

        assert len(splits) == 1
        assert splits[0] == Path("/shared/spotify_ad_2026-01-01_00-00-00.wav")

    def test_split_into_two_parts_calls_pipeline_twice(self, tmp_path: Path) -> None:
        """When split_fn returns two paths, run_pipeline is called for each."""
        audio = Path("/shared/spotify_ad_2026-01-01_00-00-00.wav")
        part1 = tmp_path / "spotify_ad_2026-01-01_00-00-00_part1.wav"
        part2 = tmp_path / "spotify_ad_2026-01-01_00-00-00_part2.wav"
        part1.touch()
        part2.touch()

        handler = AdFileHandler(
            db_path=tmp_path / "ads.db",
            split_fn=lambda _p: [part1, part2],
        )
        event = _make_closed_event(str(audio))
        with patch("src.watcher.run_pipeline") as mock_pipeline:
            mock_pipeline.return_value = MagicMock(ad_id=1)
            handler.on_closed(event)

        assert mock_pipeline.call_count == 2

    def test_split_parts_deleted_after_pipeline(self, tmp_path: Path) -> None:
        """Temp split files are removed after processing regardless of success."""
        part1 = tmp_path / "spotify_ad_test_part1.wav"
        part2 = tmp_path / "spotify_ad_test_part2.wav"
        part1.touch()
        part2.touch()
        audio = Path("/shared/spotify_ad_test.wav")

        handler = AdFileHandler(
            db_path=tmp_path / "ads.db",
            split_fn=lambda _p: [part1, part2],
        )
        event = _make_closed_event(str(audio))
        with patch("src.watcher.run_pipeline") as mock_pipeline:
            mock_pipeline.return_value = MagicMock(ad_id=1)
            handler.on_closed(event)

        assert not part1.exists()
        assert not part2.exists()

    def test_split_parts_deleted_even_on_pipeline_error(self, tmp_path: Path) -> None:
        """Temp split files are cleaned up even when the pipeline raises."""
        part1 = tmp_path / "spotify_ad_test_part1.wav"
        part2 = tmp_path / "spotify_ad_test_part2.wav"
        part1.touch()
        part2.touch()
        audio = Path("/shared/spotify_ad_test.wav")

        handler = AdFileHandler(
            db_path=tmp_path / "ads.db",
            split_fn=lambda _p: [part1, part2],
        )
        event = _make_closed_event(str(audio))
        with patch("src.watcher.run_pipeline") as mock_pipeline:
            mock_pipeline.side_effect = RuntimeError("pipeline failed")
            handler.on_closed(event)  # must not propagate

        assert not part1.exists()
        assert not part2.exists()

    def test_empty_split_result_falls_back_to_original(self, tmp_path: Path) -> None:
        """When split_fn returns [], the handler falls back to the original file."""
        audio = "/shared/spotify_ad_empty_split.wav"
        handler = AdFileHandler(
            db_path=tmp_path / "ads.db",
            split_fn=lambda _p: [],
        )
        event = _make_closed_event(audio)
        with patch("src.watcher.run_pipeline") as mock_pipeline:
            mock_pipeline.return_value = MagicMock(ad_id=1)
            handler.on_closed(event)

        mock_pipeline.assert_called_once_with(Path(audio), tmp_path / "ads.db")

    def test_split_fn_exception_does_not_propagate(self, tmp_path: Path) -> None:
        """If split_fn raises, _handle must catch and log without propagating."""
        handler = AdFileHandler(
            db_path=tmp_path / "ads.db",
            split_fn=lambda _p: (_ for _ in ()).throw(OSError("corrupt WAV")),  # type: ignore[arg-type]
        )
        event = _make_closed_event("/shared/spotify_ad_corrupt.wav")
        with patch("src.watcher.run_pipeline") as mock_pipeline:
            handler.on_closed(event)  # must not propagate
        mock_pipeline.assert_not_called()

    def test_split_fn_exception_allows_retry(self, tmp_path: Path) -> None:
        """After split_fn failure the file is removed from _seen for retry."""
        src = "/shared/spotify_ad_corrupt.wav"
        handler = AdFileHandler(
            db_path=tmp_path / "ads.db",
            split_fn=lambda _p: (_ for _ in ()).throw(OSError("corrupt WAV")),  # type: ignore[arg-type]
        )
        event = _make_closed_event(src)
        with patch("src.watcher.run_pipeline"):
            handler.on_closed(event)

        seen: dict[str, None] = handler._seen  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert src not in seen

    def test_on_modified_triggers_pipeline_in_polling_mode(
        self, tmp_path: Path
    ) -> None:
        """on_modified must trigger the pipeline in polling mode (mid-write retry)."""
        handler = self._make_handler(tmp_path, polling=True)
        event = _make_closed_event("/shared/spotify_ad_2026-01-01_00-00-00.wav")

        with patch("src.watcher.run_pipeline") as mock_pipeline:
            mock_pipeline.return_value = MagicMock(ad_id=1)
            handler.on_modified(event)

        mock_pipeline.assert_called_once()

    def test_on_modified_ignored_in_inotify_mode(self, tmp_path: Path) -> None:
        """on_modified must be a no-op when polling=False (inotify Observer mode)."""
        handler = self._make_handler(tmp_path, polling=False)
        event = _make_closed_event("/shared/spotify_ad_2026-01-01_00-00-00.wav")

        with patch("src.watcher.run_pipeline") as mock_pipeline:
            handler.on_modified(event)

        mock_pipeline.assert_not_called()

    def test_eoferror_in_split_fn_logs_warning_and_allows_retry(
        self, tmp_path: Path
    ) -> None:
        """EOFError (mid-write detection) must log WARNING and allow retry via _seen."""
        src = "/shared/spotify_ad_still_recording.wav"
        handler = AdFileHandler(
            db_path=tmp_path / "ads.db",
            polling=True,
            split_fn=lambda _p: (_ for _ in ()).throw(EOFError()),  # type: ignore[arg-type]
        )
        event = _make_closed_event(src)
        with patch("src.watcher.run_pipeline"):
            handler.on_created(event)

        # File must not remain in _seen so on_modified can retry.
        seen: dict[str, None] = handler._seen  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert src not in seen

    def test_eoferror_retried_via_on_modified(self, tmp_path: Path) -> None:
        """After EOFError on on_created, on_modified must successfully process."""
        src = "/shared/spotify_ad_2026-01-01_00-00-00.wav"
        call_count = 0

        def split_fn_that_fails_once(p: Path) -> list[Path]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise EOFError
            return [p]

        handler = AdFileHandler(
            db_path=tmp_path / "ads.db",
            polling=True,
            split_fn=split_fn_that_fails_once,
        )
        event = _make_closed_event(src)

        with patch("src.watcher.run_pipeline") as mock_pipeline:
            mock_pipeline.return_value = MagicMock(ad_id=1)
            handler.on_created(event)  # fails with EOFError → WARNING
            handler.on_modified(event)  # file now complete → succeeds

        mock_pipeline.assert_called_once()


# ---------------------------------------------------------------------------
# start_watcher
# ---------------------------------------------------------------------------


class TestStartWatcher:
    def test_returns_started_observer(self, tmp_path: Path) -> None:
        with (
            patch("src.watcher.Observer") as mock_cls,
            patch("src.watcher.config") as mock_config,
        ):
            mock_config.WATCHDOG_FORCE_POLLING = False
            mock_obs = MagicMock()
            mock_cls.return_value = mock_obs

            result = start_watcher(watch_dir=tmp_path, db_path=tmp_path / "ads.db")

        assert result is mock_obs
        mock_obs.start.assert_called_once()

    def test_schedules_handler_on_watch_dir(self, tmp_path: Path) -> None:
        with (
            patch("src.watcher.Observer") as mock_cls,
            patch("src.watcher.config") as mock_config,
        ):
            mock_config.WATCHDOG_FORCE_POLLING = False
            mock_obs = MagicMock()
            mock_cls.return_value = mock_obs

            _ = start_watcher(watch_dir=tmp_path, db_path=tmp_path / "ads.db")

        mock_obs.schedule.assert_called_once()
        _args, kwargs = mock_obs.schedule.call_args
        assert kwargs.get("recursive") is False or _args[-1] is False

    def test_creates_watch_dir_if_missing(self, tmp_path: Path) -> None:
        watch_dir = tmp_path / "new_shared"
        with (
            patch("src.watcher.Observer"),
            patch("src.watcher.config") as mock_config,
        ):
            mock_config.WATCHDOG_FORCE_POLLING = False
            _ = start_watcher(watch_dir=watch_dir, db_path=tmp_path / "ads.db")

        assert watch_dir.is_dir()

        assert watch_dir.is_dir()

    def test_default_watch_dir_from_config(self, tmp_path: Path) -> None:
        with (
            patch("src.watcher.Observer") as mock_cls,
            patch("src.watcher.config") as mock_config,
        ):
            mock_config.SHARED_DIR = tmp_path / "shared"
            mock_config.DATA_DIR = tmp_path / "data"
            mock_config.WATCHDOG_FORCE_POLLING = False
            mock_obs = MagicMock()
            mock_cls.return_value = mock_obs

            _ = start_watcher()

        mock_obs.start.assert_called_once()
        assert (tmp_path / "shared").is_dir()

    def test_polling_observer_when_force_polling(self, tmp_path: Path) -> None:
        with (
            patch("src.watcher.PollingObserver") as mock_cls,
            patch("src.watcher.config") as mock_config,
        ):
            mock_config.SHARED_DIR = tmp_path / "shared"
            mock_config.DATA_DIR = tmp_path / "data"
            mock_config.WATCHDOG_FORCE_POLLING = True
            mock_obs = MagicMock()
            mock_cls.return_value = mock_obs

            _ = start_watcher()

        mock_obs.start.assert_called_once()
