from __future__ import annotations

from typing import TYPE_CHECKING, override

from faster_whisper import WhisperModel

from src import config

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from faster_whisper.transcribe import Segment, TranscriptionInfo


class TranscriptSegment:
    """A single timestamped segment from a transcription."""

    __slots__: tuple[str, ...] = ("end_sec", "speaker", "start_sec", "text")
    text: str
    start_sec: float
    end_sec: float
    speaker: str

    def __init__(
        self, *, text: str, start_sec: float, end_sec: float, speaker: str = ""
    ) -> None:
        self.text = text
        self.start_sec = start_sec
        self.end_sec = end_sec
        self.speaker = speaker

    @override
    def __repr__(self) -> str:
        return (
            f"TranscriptSegment(text={self.text!r}, "
            f"start_sec={self.start_sec}, end_sec={self.end_sec})"
        )


class TranscriptResult:
    """Full transcription result for one audio file."""

    __slots__: tuple[str, ...] = ("language", "segments", "whisper_model")
    segments: list[TranscriptSegment]
    language: str
    whisper_model: str

    def __init__(
        self,
        *,
        segments: list[TranscriptSegment],
        language: str,
        whisper_model: str,
    ) -> None:
        self.segments = segments
        self.language = language
        self.whisper_model = whisper_model

    @property
    def full_text(self) -> str:
        return " ".join(s.text.strip() for s in self.segments)


def _load_model(model_size: str) -> WhisperModel:
    """Load a faster-whisper model on CPU."""
    return WhisperModel(model_size, device="cpu", compute_type="int8")


def transcribe(
    audio_path: Path, *, model: WhisperModel | None = None
) -> TranscriptResult:
    """Transcribe *audio_path* and return a :class:`TranscriptResult`.

    Parameters
    ----------
    audio_path:
        Path to the WAV (or any audio) file to transcribe.
    model:
        Pre-loaded :class:`WhisperModel` instance.  When *None* (default),
        a new model is loaded using :data:`src.config.WHISPER_MODEL`.
    """
    if model is None:
        model = _load_model(config.WHISPER_MODEL)

    segments_iter: Iterable[Segment]
    info: TranscriptionInfo
    segments_iter, info = model.transcribe(  # pyright: ignore[reportUnknownMemberType]
        str(audio_path), beam_size=5
    )

    segments: list[TranscriptSegment] = [
        TranscriptSegment(
            text=seg.text,
            start_sec=seg.start,
            end_sec=seg.end,
        )
        for seg in segments_iter
    ]

    return TranscriptResult(
        segments=segments,
        language=info.language,
        whisper_model=config.WHISPER_MODEL,
    )
