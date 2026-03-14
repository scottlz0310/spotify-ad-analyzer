from __future__ import annotations

import logging
import traceback
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol, override

from src import db
from src.diarizer import DiarizationResult, diarize
from src.embedder import EmbeddingResult, embed, embedding_to_blob
from src.transcriber import TranscriptResult, transcribe

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)


class _TranscribeFnProtocol(Protocol):
    """Callable protocol for the transcription stage."""

    def __call__(self, audio_path: Path, /) -> TranscriptResult: ...


class _DiarizeFnProtocol(Protocol):
    """Callable protocol for the diarization stage."""

    def __call__(self, audio_path: Path, /) -> DiarizationResult: ...


class _EmbedFnProtocol(Protocol):
    """Callable protocol for the voice-embedding stage."""

    def __call__(self, audio_path: Path, /) -> EmbeddingResult: ...


class PipelineResult:
    """Result of running the full analysis pipeline on one audio file."""

    __slots__: tuple[str, ...] = ("ad_id", "diarization", "embeddings", "transcript")
    ad_id: int
    transcript: TranscriptResult
    diarization: DiarizationResult
    embeddings: dict[str, EmbeddingResult]

    def __init__(
        self,
        *,
        ad_id: int,
        transcript: TranscriptResult,
        diarization: DiarizationResult,
        embeddings: dict[str, EmbeddingResult],
    ) -> None:
        self.ad_id = ad_id
        self.transcript = transcript
        self.diarization = diarization
        self.embeddings = embeddings

    @override
    def __repr__(self) -> str:
        return (
            f"PipelineResult(ad_id={self.ad_id},"
            f" speakers={self.diarization.speakers!r})"
        )


def _assign_speakers(
    transcript: TranscriptResult,
    diarization: DiarizationResult,
) -> list[db.SegmentInsert]:
    """Merge transcript segments with diarization speakers by maximum time overlap.

    Each transcript segment is assigned the speaker whose diarization interval
    has the greatest overlap with the segment.  Segments with no overlap
    receive an empty speaker label.
    """
    result: list[db.SegmentInsert] = []
    for t_seg in transcript.segments:
        speaker = ""
        best_overlap = 0.0
        for d_seg in diarization.segments:
            overlap = min(t_seg.end_sec, d_seg.end_sec) - max(
                t_seg.start_sec, d_seg.start_sec
            )
            if overlap > best_overlap:
                best_overlap = overlap
                speaker = d_seg.speaker
        result.append(
            db.SegmentInsert(
                speaker=speaker,
                text=t_seg.text,
                start_sec=t_seg.start_sec,
                end_sec=t_seg.end_sec,
            )
        )
    return result


def _default_transcribe(audio_path: Path, /) -> TranscriptResult:
    return transcribe(audio_path)


def _default_diarize(audio_path: Path, /) -> DiarizationResult:
    return diarize(audio_path)


def _default_embed(audio_path: Path, /) -> EmbeddingResult:
    return embed(audio_path)


def run_pipeline(  # noqa: PLR0913
    audio_path: Path,
    db_path: Path,
    *,
    recorded_at: str | None = None,
    transcribe_fn: _TranscribeFnProtocol | None = None,
    diarize_fn: _DiarizeFnProtocol | None = None,
    embed_fn: _EmbedFnProtocol | None = None,
) -> PipelineResult:
    """Run the full analysis pipeline on *audio_path* and persist results.

    Parameters
    ----------
    audio_path:
        WAV file to analyze.
    db_path:
        Path to the SQLite database.  Must already be initialized with
        :func:`src.db.init_db`.
    recorded_at:
        ISO-8601 timestamp for when the ad was recorded.  Defaults to the
        file's last-modified time.
    transcribe_fn / diarize_fn / embed_fn:
        Callable overrides for each pipeline stage (used in tests).

    Returns
    -------
    PipelineResult
        Contains the ad_id, transcript, diarization, and voice embeddings.

    Raises
    ------
    Exception
        Any exception from the pipeline stages is re-raised after setting
        the ad status to ``'error'`` in the database.
    """
    if recorded_at is None:
        mtime = audio_path.stat().st_mtime
        recorded_at = datetime.fromtimestamp(mtime, tz=UTC).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

    _transcribe: _TranscribeFnProtocol = (
        transcribe_fn if transcribe_fn is not None else _default_transcribe
    )
    _diarize: _DiarizeFnProtocol = (
        diarize_fn if diarize_fn is not None else _default_diarize
    )
    _embed: _EmbedFnProtocol = embed_fn if embed_fn is not None else _default_embed

    filename = audio_path.name

    with db.connect(db_path) as conn:
        ad_id = db.insert_ad(conn, filename, recorded_at)
        db.update_ad_status(conn, ad_id, "processing")

    try:
        transcript = _transcribe(audio_path)
        diarization = _diarize(audio_path)
        embedding_result = _embed(audio_path)
        embedding_blob = embedding_to_blob(embedding_result.embedding)

        speakers = diarization.speakers or [""]
        segments = _assign_speakers(transcript, diarization)

        with db.connect(db_path) as conn:
            db.upsert_transcript(
                conn,
                ad_id,
                transcript.full_text,
                transcript.language,
                transcript.whisper_model,
            )
            db.insert_segments(conn, ad_id, segments)
            for speaker in speakers:
                db.upsert_voice_embedding(conn, ad_id, speaker, embedding_blob)
            db.update_ad_status(conn, ad_id, "done")

    except Exception as exc:
        _logger.exception("Pipeline failed for %s (ad_id=%d)", audio_path, ad_id)
        with db.connect(db_path) as conn:
            db.update_ad_status(
                conn, ad_id, "error", error_message=traceback.format_exc()
            )
        msg = f"Pipeline failed for {audio_path.name}"
        raise RuntimeError(msg) from exc

    return PipelineResult(
        ad_id=ad_id,
        transcript=transcript,
        diarization=diarization,
        embeddings=dict.fromkeys(speakers, embedding_result),
    )
