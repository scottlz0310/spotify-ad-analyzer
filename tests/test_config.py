from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from src import config

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture
def reload_config(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[pytest.MonkeyPatch, None, None]:
    """Reload config module after monkeypatching env vars."""
    yield monkeypatch
    _ = importlib.reload(config)


def test_shared_dir_is_path(reload_config: pytest.MonkeyPatch) -> None:
    reload_config.setenv("SHARED_DIR", "/app/shared")
    _ = importlib.reload(config)
    assert isinstance(config.SHARED_DIR, Path)


def test_data_dir_is_path(reload_config: pytest.MonkeyPatch) -> None:
    reload_config.setenv("DATA_DIR", "/app/data")
    _ = importlib.reload(config)
    assert isinstance(config.DATA_DIR, Path)


def test_whisper_model_nonempty(reload_config: pytest.MonkeyPatch) -> None:
    reload_config.setenv("WHISPER_MODEL", "small")
    _ = importlib.reload(config)
    assert isinstance(config.WHISPER_MODEL, str)
    assert len(config.WHISPER_MODEL) > 0


def test_ollama_host_has_port(reload_config: pytest.MonkeyPatch) -> None:
    reload_config.setenv("OLLAMA_HOST", "localhost:11434")
    _ = importlib.reload(config)
    assert isinstance(config.OLLAMA_HOST, str)
    assert ":" in config.OLLAMA_HOST
