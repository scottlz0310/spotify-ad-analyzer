"""Tests for src/splitter.py -- WAV silence-boundary detection and splitting."""

from __future__ import annotations

import struct
import wave
from typing import TYPE_CHECKING

import pytest

from src.splitter import detect_silence_boundary, split_if_needed, split_wav

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# WAV generation helpers
# ---------------------------------------------------------------------------

_RATE = 44100
_CHANNELS = 2
_SAMPWIDTH = 2  # 16-bit
_AMPLITUDE = 8000  # speech-like noise amplitude


def _write_pcm(w: wave.Wave_write, n_frames: int, amplitude: int) -> None:
    """Write *n_frames* frames of constant-amplitude PCM to *w*."""
    sample = max(0, amplitude)
    frame = struct.pack(f"<{_CHANNELS}h", sample, sample)
    w.writeframes(frame * n_frames)


def _make_wav(
    path: Path,
    *,
    noise1_sec: float,
    silence_sec: float,
    noise2_sec: float,
    rate: int = _RATE,
) -> Path:
    """Create noise|silence|noise WAV at *path* and return it."""
    with wave.open(str(path), "w") as w:
        w.setnchannels(_CHANNELS)
        w.setsampwidth(_SAMPWIDTH)
        w.setframerate(rate)
        _write_pcm(w, int(noise1_sec * rate), _AMPLITUDE)
        _write_pcm(w, int(silence_sec * rate), 0)
        _write_pcm(w, int(noise2_sec * rate), _AMPLITUDE)
    return path


def _make_single_wav(path: Path, *, duration_sec: float) -> Path:
    """Create a single-noise WAV (no silence gap)."""
    with wave.open(str(path), "w") as w:
        w.setnchannels(_CHANNELS)
        w.setsampwidth(_SAMPWIDTH)
        w.setframerate(_RATE)
        _write_pcm(w, int(duration_sec * _RATE), _AMPLITUDE)
    return path


def _wav_duration(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


# ---------------------------------------------------------------------------
# detect_silence_boundary
# ---------------------------------------------------------------------------


class TestDetectSilenceBoundary:
    def test_detects_boundary_in_split_file(self, tmp_path: Path) -> None:
        """A 62s file with silence at 31-32s should return midpoint ~31.5s."""
        wav = _make_wav(
            tmp_path / "ad.wav",
            noise1_sec=31.0,
            silence_sec=1.0,
            noise2_sec=30.0,
        )
        result = detect_silence_boundary(wav)
        assert result is not None
        assert 30.5 <= result <= 32.5

    def test_returns_none_for_single_ad(self, tmp_path: Path) -> None:
        """A 25s file with no silence in search window returns None."""
        wav = _make_single_wav(tmp_path / "ad.wav", duration_sec=25.0)
        assert detect_silence_boundary(wav) is None

    def test_returns_none_when_silence_outside_window(self, tmp_path: Path) -> None:
        """Silence before search_start_sec is ignored."""
        wav = _make_wav(
            tmp_path / "ad.wav",
            noise1_sec=5.0,
            silence_sec=1.0,  # at 5s — before default search_start_sec=20s
            noise2_sec=50.0,
        )
        assert detect_silence_boundary(wav) is None

    def test_returns_none_when_silence_too_short(self, tmp_path: Path) -> None:
        """Silence shorter than min_silence_ms is not a boundary."""
        wav = _make_wav(
            tmp_path / "ad.wav",
            noise1_sec=30.0,
            silence_sec=0.1,  # 100ms — below default 300ms
            noise2_sec=30.0,
        )
        assert detect_silence_boundary(wav, min_silence_ms=300) is None

    def test_respects_custom_threshold(self, tmp_path: Path) -> None:
        """Threshold controls whether low-level noise counts as silence."""
        path = tmp_path / "low_mid.wav"
        with wave.open(str(path), "w") as wf:
            wf.setnchannels(_CHANNELS)
            wf.setsampwidth(_SAMPWIDTH)
            wf.setframerate(_RATE)
            _write_pcm(wf, int(30.0 * _RATE), _AMPLITUDE)  # ~8000 — loud speech
            _write_pcm(wf, int(1.0 * _RATE), 100)  # ~100 — low residual noise
            _write_pcm(wf, int(30.0 * _RATE), _AMPLITUDE)  # ~8000 — loud speech
        # threshold=500: rms≈100 < 500 → low-level noise looks silent → boundary found
        assert detect_silence_boundary(path, threshold_rms=500) is not None
        # threshold=50: rms≈100 > 50 → low-level noise is "loud" → no boundary
        assert detect_silence_boundary(path, threshold_rms=50) is None

    def test_respects_custom_search_window(self, tmp_path: Path) -> None:
        """Custom search window finds silence at a different position."""
        wav = _make_wav(
            tmp_path / "ad.wav",
            noise1_sec=60.0,
            silence_sec=1.0,  # at 60s
            noise2_sec=30.0,
        )
        # Default window (20-50s) misses it
        assert detect_silence_boundary(wav) is None
        # Extended window (50-80s) finds it
        result = detect_silence_boundary(
            wav, search_start_sec=50.0, search_end_sec=80.0
        )
        assert result is not None
        assert 59.5 <= result <= 61.5

    def test_silence_midpoint_accuracy(self, tmp_path: Path) -> None:
        """Midpoint of a 2s silence starting at 29s is near 30s."""
        wav = _make_wav(
            tmp_path / "ad.wav",
            noise1_sec=29.0,
            silence_sec=2.0,  # 29-31s -> midpoint approx 30s
            noise2_sec=30.0,
        )
        result = detect_silence_boundary(wav)
        assert result is not None
        assert 29.5 <= result <= 31.0


# ---------------------------------------------------------------------------
# split_wav
# ---------------------------------------------------------------------------


class TestSplitWav:
    def test_produces_two_files(self, tmp_path: Path) -> None:
        wav = _make_single_wav(tmp_path / "spotify_ad_test.wav", duration_sec=60.0)
        part1, part2 = split_wav(wav, 30.0, tmp_path / "split")
        assert part1.exists()
        assert part2.exists()

    def test_stem_suffixes(self, tmp_path: Path) -> None:
        wav = _make_single_wav(
            tmp_path / "spotify_ad_2026-01-01_00-00-00.wav", duration_sec=60.0
        )
        part1, part2 = split_wav(wav, 30.0, tmp_path / "split")
        assert part1.name == "spotify_ad_2026-01-01_00-00-00_part1.wav"
        assert part2.name == "spotify_ad_2026-01-01_00-00-00_part2.wav"

    def test_combined_duration_equals_original(self, tmp_path: Path) -> None:
        wav = _make_single_wav(tmp_path / "spotify_ad_test.wav", duration_sec=62.0)
        part1, part2 = split_wav(wav, 31.0, tmp_path / "split")
        original_dur = _wav_duration(wav)
        combined = _wav_duration(part1) + _wav_duration(part2)
        assert abs(combined - original_dur) < 0.05  # within 50ms

    def test_split_near_boundary(self, tmp_path: Path) -> None:
        """Part durations approximate the split point."""
        wav = _make_single_wav(tmp_path / "spotify_ad_test.wav", duration_sec=62.0)
        part1, part2 = split_wav(wav, 30.0, tmp_path / "split")
        assert abs(_wav_duration(part1) - 30.0) < 0.05
        assert abs(_wav_duration(part2) - 32.0) < 0.05

    def test_creates_output_dir(self, tmp_path: Path) -> None:
        wav = _make_single_wav(tmp_path / "spotify_ad_test.wav", duration_sec=60.0)
        out = tmp_path / "deep" / "split"
        assert not out.exists()
        _ = split_wav(wav, 30.0, out)
        assert out.is_dir()

    def test_preserves_wav_format(self, tmp_path: Path) -> None:
        """Split files retain original sample rate, channels, and sample width."""
        wav = _make_single_wav(tmp_path / "spotify_ad_test.wav", duration_sec=60.0)
        part1, _ = split_wav(wav, 30.0, tmp_path / "split")
        with wave.open(str(part1)) as w:
            assert w.getframerate() == _RATE
            assert w.getnchannels() == _CHANNELS
            assert w.getsampwidth() == _SAMPWIDTH

    def test_boundary_clamped_to_zero(self, tmp_path: Path) -> None:
        wav = _make_single_wav(tmp_path / "spotify_ad_test.wav", duration_sec=30.0)
        part1, part2 = split_wav(wav, -5.0, tmp_path / "split")
        assert _wav_duration(part1) == pytest.approx(0.0, abs=0.05)  # pyright: ignore[reportUnknownMemberType]
        assert abs(_wav_duration(part2) - 30.0) < 0.05

    def test_boundary_clamped_to_duration(self, tmp_path: Path) -> None:
        wav = _make_single_wav(tmp_path / "spotify_ad_test.wav", duration_sec=30.0)
        part1, part2 = split_wav(wav, 999.0, tmp_path / "split")
        assert abs(_wav_duration(part1) - 30.0) < 0.05
        assert _wav_duration(part2) == pytest.approx(0.0, abs=0.05)  # pyright: ignore[reportUnknownMemberType]


# ---------------------------------------------------------------------------
# split_if_needed
# ---------------------------------------------------------------------------


class TestSplitIfNeeded:
    def test_returns_original_path_for_single_ad(self, tmp_path: Path) -> None:
        wav = _make_single_wav(tmp_path / "spotify_ad_test.wav", duration_sec=25.0)
        result = split_if_needed(wav)
        assert result == [wav]

    def test_returns_two_paths_for_double_ad(self, tmp_path: Path) -> None:
        wav = _make_wav(
            tmp_path / "spotify_ad_test.wav",
            noise1_sec=30.0,
            silence_sec=1.0,
            noise2_sec=30.0,
        )
        result = split_if_needed(wav)
        assert len(result) == 2
        assert all(p.exists() for p in result)

    def test_default_output_dir_is_dot_split(self, tmp_path: Path) -> None:
        wav = _make_wav(
            tmp_path / "spotify_ad_test.wav",
            noise1_sec=30.0,
            silence_sec=1.0,
            noise2_sec=30.0,
        )
        result = split_if_needed(wav)
        assert len(result) == 2
        assert result[0].parent == tmp_path / ".split"

    def test_custom_output_dir(self, tmp_path: Path) -> None:
        wav = _make_wav(
            tmp_path / "spotify_ad_test.wav",
            noise1_sec=30.0,
            silence_sec=1.0,
            noise2_sec=30.0,
        )
        out_dir = tmp_path / "parts"
        result = split_if_needed(wav, out_dir)
        assert result[0].parent == out_dir

    def test_part_filenames_use_suffix(self, tmp_path: Path) -> None:
        wav = _make_wav(
            tmp_path / "spotify_ad_2026-01-01_00-00-00.wav",
            noise1_sec=30.0,
            silence_sec=1.0,
            noise2_sec=30.0,
        )
        result = split_if_needed(wav)
        assert result[0].name == "spotify_ad_2026-01-01_00-00-00_part1.wav"
        assert result[1].name == "spotify_ad_2026-01-01_00-00-00_part2.wav"

    def test_no_split_below_min_silence(self, tmp_path: Path) -> None:
        """100ms silence is below default 300ms threshold → no split."""
        wav = _make_wav(
            tmp_path / "spotify_ad_test.wav",
            noise1_sec=30.0,
            silence_sec=0.1,
            noise2_sec=30.0,
        )
        result = split_if_needed(wav)
        assert result == [wav]
