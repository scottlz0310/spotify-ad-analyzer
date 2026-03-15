"""WAV file splitter: silence-based boundary detection for concatenated ads.

Spotify ad breaks often contain two consecutive 30-second ads in a single
recording.  This module detects the silent gap between them and splits the
file into individual parts for per-ad analysis.
"""

from __future__ import annotations

import logging
import struct
import wave
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)

_CHUNK_MS = 100  # RMS window size in milliseconds


def _rms_chunks(
    audio_path: Path,
    chunk_ms: int = _CHUNK_MS,
) -> list[tuple[float, float]]:
    """Return list of (time_sec, rms) for each ``chunk_ms``-ms window."""
    results: list[tuple[float, float]] = []
    with wave.open(str(audio_path)) as w:
        rate = w.getframerate()
        channels = w.getnchannels()
        sampwidth = w.getsampwidth()
        chunk_frames = int(rate * chunk_ms / 1000)
        t = 0.0
        while True:
            data = w.readframes(chunk_frames)
            if not data:
                break
            n = len(data) // sampwidth // channels
            if n == 0:
                break
            raw = data[: n * channels * sampwidth]
            samples = struct.unpack(f"<{n * channels}h", raw)
            mono = [samples[i * channels] for i in range(n)]
            rms = (sum(s * s for s in mono) / len(mono)) ** 0.5
            results.append((t, rms))
            t += chunk_ms / 1000
    return results


def detect_silence_boundary(
    audio_path: Path,
    *,
    threshold_rms: int = 500,
    min_silence_ms: int = 300,
    search_start_sec: float = 20.0,
    search_end_sec: float = 50.0,
) -> float | None:
    """Return the midpoint of the first qualifying silence, or ``None``.

    Scans the audio file for a continuous silent region of at least
    *min_silence_ms* within the window [*search_start_sec*, *search_end_sec*].
    Returns the midpoint of that region (in seconds) as the recommended split
    point, or ``None`` if no such region is found.

    Parameters
    ----------
    audio_path:
        WAV file to analyse.
    threshold_rms:
        RMS amplitude below which a chunk is considered silent.
    min_silence_ms:
        Minimum consecutive silence duration (ms) to be treated as a boundary.
    search_start_sec:
        Earliest position (s) to begin searching for a boundary.
    search_end_sec:
        Latest position (s) to stop searching.
    """
    chunks = _rms_chunks(audio_path)
    silence_start: float | None = None

    for t, rms in chunks:
        in_window = search_start_sec <= t <= search_end_sec

        if rms < threshold_rms:
            if in_window and silence_start is None:
                silence_start = t
        elif silence_start is not None:
            duration_ms = (t - silence_start) * 1000
            if duration_ms >= min_silence_ms:
                midpoint = (silence_start + t) / 2
                _logger.debug(
                    "Silence boundary: %.2f-%.2fs (%.0fms) -> split at %.2fs in %s",
                    silence_start,
                    t,
                    duration_ms,
                    midpoint,
                    audio_path.name,
                )
                return midpoint
            silence_start = None

    # Silence may extend to the end of the search window.
    if silence_start is not None:
        last_t = chunks[-1][0] if chunks else 0.0
        end = min(search_end_sec, last_t)
        duration_ms = (end - silence_start) * 1000
        if duration_ms >= min_silence_ms:
            return (silence_start + end) / 2

    return None


def split_wav(
    audio_path: Path,
    boundary_sec: float,
    output_dir: Path,
) -> tuple[Path, Path]:
    """Split *audio_path* at *boundary_sec* and write two files to *output_dir*.

    Output filenames are ``<stem>_part1.wav`` and ``<stem>_part2.wav``.

    Parameters
    ----------
    audio_path:
        Source WAV file.
    boundary_sec:
        Split point in seconds.  Clamped to [0, duration].
    output_dir:
        Directory for the output files.  Created if it does not exist.

    Returns
    -------
    tuple[Path, Path]
        Paths to the first and second parts, respectively.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = audio_path.stem
    part1_path = output_dir / f"{stem}_part1.wav"
    part2_path = output_dir / f"{stem}_part2.wav"

    with wave.open(str(audio_path)) as w:
        rate = w.getframerate()
        channels = w.getnchannels()
        sampwidth = w.getsampwidth()
        n_frames = w.getnframes()

        boundary_frame = max(0, min(int(boundary_sec * rate), n_frames))
        bytes_per_frame = channels * sampwidth

        w.setpos(0)
        all_data = w.readframes(n_frames)

    split_byte = boundary_frame * bytes_per_frame
    part1_data = all_data[:split_byte]
    part2_data = all_data[split_byte:]

    def _write(path: Path, data: bytes) -> None:
        with wave.open(str(path), "w") as out:
            out.setnchannels(channels)
            out.setsampwidth(sampwidth)
            out.setframerate(rate)
            out.writeframes(data)

    _write(part1_path, part1_data)
    _write(part2_path, part2_data)
    return part1_path, part2_path


def split_if_needed(
    audio_path: Path,
    output_dir: Path | None = None,
    *,
    threshold_rms: int = 500,
    min_silence_ms: int = 300,
    search_window: tuple[float, float] = (20.0, 50.0),
) -> list[Path]:
    """Return ``[audio_path]`` if no split is needed, else ``[part1, part2]``.

    Detects whether *audio_path* contains two concatenated ads separated by a
    silence gap and splits it if so.  Split files are written to *output_dir*
    (defaults to ``audio_path.parent / ".split"``).  The caller is responsible
    for cleaning up split files after processing.

    Parameters
    ----------
    audio_path:
        WAV file to inspect and possibly split.
    output_dir:
        Directory for split output.  Defaults to ``audio_path.parent / ".split"``.
    threshold_rms:
        Forwarded to :func:`detect_silence_boundary`.
    min_silence_ms:
        Forwarded to :func:`detect_silence_boundary`.
    search_window:
        ``(start_sec, end_sec)`` window to search for a silence boundary.
        Forwarded to :func:`detect_silence_boundary` as *search_start_sec* and
        *search_end_sec*.
    """
    boundary = detect_silence_boundary(
        audio_path,
        threshold_rms=threshold_rms,
        min_silence_ms=min_silence_ms,
        search_start_sec=search_window[0],
        search_end_sec=search_window[1],
    )

    if boundary is None:
        _logger.debug("No split boundary in %s - single ad", audio_path.name)
        return [audio_path]

    if output_dir is None:
        output_dir = audio_path.parent / ".split"

    part1, part2 = split_wav(audio_path, boundary, output_dir)
    _logger.info(
        "Split %s at %.2fs -> %s, %s",
        audio_path.name,
        boundary,
        part1.name,
        part2.name,
    )
    return [part1, part2]
