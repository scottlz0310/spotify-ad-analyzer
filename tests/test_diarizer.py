"""Tests for src/diarizer.py.

All tests mock :class:`pyannote.audio.Pipeline` to avoid loading real model
weights during CI.  The fixture ``sample.wav`` is a 0.5-second silent WAV
used to supply a realistic :class:`~pathlib.Path` argument to ``diarize()``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from src import diarizer

if TYPE_CHECKING:
    import pytest

# -- helpers --

SAMPLE_WAV = Path(__file__).parent / "fixtures" / "sample.wav"


def _make_turn(start: float, end: float) -> MagicMock:
    turn = MagicMock()
    turn.start = start
    turn.end = end
    return turn


def _make_annotation(*items: tuple[float, float, str]) -> MagicMock:
    """Return a mock annotation whose ``itertracks`` yields ``(turn, track, label)``."""
    annotation = MagicMock()
    annotation.itertracks.return_value = iter(
        [(_make_turn(s, e), "A", sp) for s, e, sp in items]
    )
    return annotation


def _make_pipeline(*items: tuple[float, float, str]) -> MagicMock:
    """Return a mock pipeline that returns a mock annotation when called."""
    pipeline = MagicMock()
    pipeline.return_value = _make_annotation(*items)
    return pipeline


# -- DiarizationSegment tests --


def test_segment_attributes() -> None:
    seg = diarizer.DiarizationSegment(speaker="SPEAKER_00", start_sec=0.0, end_sec=2.5)
    assert seg.speaker == "SPEAKER_00"
    assert seg.start_sec == 0.0
    assert seg.end_sec == 2.5


def test_segment_repr() -> None:
    seg = diarizer.DiarizationSegment(speaker="SPEAKER_01", start_sec=1.0, end_sec=3.0)
    assert "SPEAKER_01" in repr(seg)


# -- DiarizationResult tests --


def test_result_speakers_unique_sorted() -> None:
    segs = [
        diarizer.DiarizationSegment(speaker="SPEAKER_01", start_sec=0.0, end_sec=1.0),
        diarizer.DiarizationSegment(speaker="SPEAKER_00", start_sec=1.0, end_sec=2.0),
        diarizer.DiarizationSegment(speaker="SPEAKER_01", start_sec=2.0, end_sec=3.0),
    ]
    result = diarizer.DiarizationResult(
        segments=segs, model_name="pyannote/speaker-diarization-3.1"
    )
    assert result.speakers == ["SPEAKER_00", "SPEAKER_01"]


def test_result_speakers_empty() -> None:
    result = diarizer.DiarizationResult(segments=[], model_name="any")
    assert result.speakers == []


# -- diarize function tests --


def test_diarize_returns_result() -> None:
    pl = _make_pipeline((0.0, 1.0, "SPEAKER_00"), (1.0, 2.5, "SPEAKER_01"))
    result = diarizer.diarize(SAMPLE_WAV, pipeline=pl)
    assert isinstance(result, diarizer.DiarizationResult)
    assert len(result.segments) == 2


def test_diarize_segment_values() -> None:
    pl = _make_pipeline((0.5, 1.8, "SPEAKER_00"))
    result = diarizer.diarize(SAMPLE_WAV, pipeline=pl)
    seg = result.segments[0]
    assert seg.speaker == "SPEAKER_00"
    assert seg.start_sec == 0.5
    assert seg.end_sec == 1.8


def test_diarize_empty_audio() -> None:
    pl = _make_pipeline()
    result = diarizer.diarize(SAMPLE_WAV, pipeline=pl)
    assert result.segments == []
    assert result.speakers == []


def test_diarize_uses_config_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.config.DIARIZE_MODEL", "pyannote/speaker-diarization-3.1")
    pl = _make_pipeline((0.0, 1.0, "SPEAKER_00"))
    result = diarizer.diarize(SAMPLE_WAV, pipeline=pl)
    assert result.model_name == "pyannote/speaker-diarization-3.1"


def test_diarize_explicit_model_name() -> None:
    pl = _make_pipeline((0.0, 1.0, "SPEAKER_00"))
    result = diarizer.diarize(
        SAMPLE_WAV, pipeline=pl, model_name="pyannote/speaker-diarization-2.1"
    )
    assert result.model_name == "pyannote/speaker-diarization-2.1"


def test_diarize_loads_pipeline_when_none(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_pipeline = _make_pipeline((0.0, 1.0, "SPEAKER_00"))
    with patch("src.diarizer._load_pipeline", return_value=mock_pipeline) as mock_load:
        monkeypatch.setattr(
            "src.config.DIARIZE_MODEL", "pyannote/speaker-diarization-3.1"
        )
        monkeypatch.setattr("src.config.HF_TOKEN", "hf_test_token")
        _ = diarizer.diarize(SAMPLE_WAV)
        mock_load.assert_called_once_with(
            "pyannote/speaker-diarization-3.1", "hf_test_token"
        )


def test_diarize_calls_pipeline_with_str_path() -> None:
    pl = _make_pipeline()
    _ = diarizer.diarize(SAMPLE_WAV, pipeline=pl)
    pl.assert_called_once_with(str(SAMPLE_WAV))
