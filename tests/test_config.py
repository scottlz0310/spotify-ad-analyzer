from __future__ import annotations

from pathlib import Path

from src import config


def test_shared_dir_is_path() -> None:
    assert isinstance(config.SHARED_DIR, Path)


def test_data_dir_is_path() -> None:
    assert isinstance(config.DATA_DIR, Path)


def test_whisper_model_nonempty() -> None:
    assert isinstance(config.WHISPER_MODEL, str)
    assert len(config.WHISPER_MODEL) > 0


def test_ollama_host_has_port() -> None:
    assert isinstance(config.OLLAMA_HOST, str)
    assert ":" in config.OLLAMA_HOST
