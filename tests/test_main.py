from __future__ import annotations

import threading
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from pathlib import Path

from src.main import main


class TestMain:
    def test_main_calls_init_db(self, tmp_path: Path) -> None:
        stop_event = threading.Event()
        stop_event.set()

        with (
            patch("src.main.db.init_db") as mock_init,
            patch("src.main.start_watcher", return_value=MagicMock()),
            patch("src.main.config") as mock_config,
            patch("src.main.threading.Event", return_value=stop_event),
            patch("src.main.signal.signal"),
        ):
            mock_config.DATA_DIR = tmp_path
            mock_config.SHARED_DIR = tmp_path / "shared"
            main()

        mock_init.assert_called_once_with(tmp_path / "ads.db")

    def test_main_starts_and_stops_observer(self, tmp_path: Path) -> None:
        stop_event = threading.Event()
        stop_event.set()

        mock_observer = MagicMock()

        with (
            patch("src.main.db.init_db"),
            patch("src.main.start_watcher", return_value=mock_observer),
            patch("src.main.config") as mock_config,
            patch("src.main.threading.Event", return_value=stop_event),
            patch("src.main.signal.signal"),
        ):
            mock_config.DATA_DIR = tmp_path
            mock_config.SHARED_DIR = tmp_path / "shared"
            main()

        mock_observer.stop.assert_called_once()
        mock_observer.join.assert_called_once()

    def test_main_registers_signal_handlers(self, tmp_path: Path) -> None:
        stop_event = threading.Event()
        stop_event.set()

        with (
            patch("src.main.db.init_db"),
            patch("src.main.start_watcher", return_value=MagicMock()),
            patch("src.main.config") as mock_config,
            patch("src.main.threading.Event", return_value=stop_event),
            patch("src.main.signal.signal") as mock_signal,
        ):
            mock_config.DATA_DIR = tmp_path
            mock_config.SHARED_DIR = tmp_path / "shared"
            main()

        assert mock_signal.call_count == 2
