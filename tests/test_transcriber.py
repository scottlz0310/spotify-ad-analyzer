"""Tests for src/transcriber.py.

All tests mock :class:`faster_whisper.WhisperModel` to avoid loading real
model weights during CI.  The fixture ``sample.wav`` is a 0.5-second silent
WAV used only to satisfy path-existence checks.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from src import transcriber

if TYPE_CHECKING:
    import pytest

# -- helpers --

SAMPLE_WAV = Path(__file__).parent / "fixtures" / "sample.wav"


def _make_segment(text: str, start: float, end: float) -> MagicMock:
    seg = MagicMock()
    seg.text = text
    seg.start = start
    seg.end = end
    return seg


def _make_info(language: str = "ja") -> MagicMock:
    info = MagicMock()
    info.language = language
    return info


def _make_model(*segments: MagicMock, language: str = "ja") -> MagicMock:
    model = MagicMock()
    model.transcribe.return_value = (iter(segments), _make_info(language))
    return model


# -- TranscriptSegment tests --


def test_segment_attributes() -> None:
    seg = transcriber.TranscriptSegment(text="hello", start_sec=0.0, end_sec=1.5)
    assert seg.text == "hello"
    assert seg.start_sec == 0.0
    assert seg.end_sec == 1.5
    assert seg.speaker == ""


def test_segment_speaker() -> None:
    seg = transcriber.TranscriptSegment(
        text="hi", start_sec=0.0, end_sec=1.0, speaker="SPEAKER_00"
    )
    assert seg.speaker == "SPEAKER_00"


def test_segment_repr() -> None:
    seg = transcriber.TranscriptSegment(text="hi", start_sec=0.0, end_sec=1.0)
    assert "hi" in repr(seg)


# -- TranscriptResult tests --


def test_result_full_text_single() -> None:
    segs = [transcriber.TranscriptSegment(text=" hello ", start_sec=0.0, end_sec=1.0)]
    result = transcriber.TranscriptResult(
        segments=segs, language="en", whisper_model="small"
    )
    assert result.full_text == "hello"


def test_result_full_text_multiple() -> None:
    segs = [
        transcriber.TranscriptSegment(text=" foo ", start_sec=0.0, end_sec=1.0),
        transcriber.TranscriptSegment(text=" bar ", start_sec=1.0, end_sec=2.0),
    ]
    result = transcriber.TranscriptResult(
        segments=segs, language="en", whisper_model="small"
    )
    assert result.full_text == "foo bar"


def test_result_full_text_empty() -> None:
    result = transcriber.TranscriptResult(
        segments=[], language="en", whisper_model="tiny"
    )
    assert result.full_text == ""


# -- transcribe function tests --


def test_transcribe_returns_result() -> None:
    model = _make_model(
        _make_segment(" こんにちは ", 0.0, 1.2),
        _make_segment(" 世界 ", 1.2, 2.5),
        language="ja",
    )
    result = transcriber.transcribe(SAMPLE_WAV, model=model)
    assert isinstance(result, transcriber.TranscriptResult)
    assert len(result.segments) == 2
    assert result.language == "ja"


def test_transcribe_segment_values() -> None:
    model = _make_model(_make_segment(" test ", 0.5, 1.5))
    result = transcriber.transcribe(SAMPLE_WAV, model=model)
    seg = result.segments[0]
    assert seg.text == " test "
    assert seg.start_sec == 0.5
    assert seg.end_sec == 1.5
    assert seg.speaker == ""


def test_transcribe_empty_audio() -> None:
    model = _make_model()  # no segments
    result = transcriber.transcribe(SAMPLE_WAV, model=model)
    assert result.segments == []
    assert result.full_text == ""


def test_transcribe_uses_config_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.config.WHISPER_MODEL", "tiny")
    model = _make_model(_make_segment(" x ", 0.0, 0.5))
    result = transcriber.transcribe(SAMPLE_WAV, model=model)
    assert result.whisper_model == "tiny"


def test_transcribe_calls_model_with_path() -> None:
    model = _make_model()
    _ = transcriber.transcribe(SAMPLE_WAV, model=model)
    model.transcribe.assert_called_once_with(str(SAMPLE_WAV), beam_size=5)


def test_transcribe_loads_model_when_none(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_model = _make_model(_make_segment(" hi ", 0.0, 1.0))
    with patch("src.transcriber._load_model", return_value=mock_model) as mock_load:
        monkeypatch.setattr("src.config.WHISPER_MODEL", "base")
        _ = transcriber.transcribe(SAMPLE_WAV)
        mock_load.assert_called_once_with("base")


def test_transcribe_explicit_whisper_model() -> None:
    model = _make_model(_make_segment(" x ", 0.0, 0.5))
    result = transcriber.transcribe(SAMPLE_WAV, model=model, whisper_model="large-v3")
    assert result.whisper_model == "large-v3"
