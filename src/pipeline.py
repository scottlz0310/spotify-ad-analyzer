from __future__ import annotations

import logging
import traceback
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol, override

from src import db
from src.diarizer import DiarizationResult, diarize
from src.embedder import EmbeddingResult, embed, embedding_to_blob
from src.llm_analyzer import LlmAnalysisResult, OllamaError, analyze_transcript
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


class _AnalyzeFnProtocol(Protocol):
    """Callable protocol for the LLM analysis stage."""

    def __call__(self, transcript: str, /) -> LlmAnalysisResult | None: ...


class PipelineResult:
    """Result of running the full analysis pipeline on one audio file."""

    __slots__: tuple[str, ...] = (
        "ad_id",
        "diarization",
        "embeddings",
        "llm_analysis",
        "transcript",
    )
    ad_id: int
    transcript: TranscriptResult
    diarization: DiarizationResult
    embeddings: dict[str, EmbeddingResult]
    llm_analysis: LlmAnalysisResult | None

    def __init__(
        self,
        *,
        ad_id: int,
        transcript: TranscriptResult,
        diarization: DiarizationResult,
        embeddings: dict[str, EmbeddingResult],
        llm_analysis: LlmAnalysisResult | None = None,
    ) -> None:
        self.ad_id = ad_id
        self.transcript = transcript
        self.diarization = diarization
        self.embeddings = embeddings
        self.llm_analysis = llm_analysis

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

    Both lists are assumed to be ordered by start time.  A two-pointer scan
    skips diarization segments that end before each transcript segment starts,
    reducing comparisons to O(N+M) in the typical ordered case.
    """
    result: list[db.SegmentInsert] = []
    d_segs = diarization.segments
    d_len = len(d_segs)
    d_base = 0  # leftmost candidate index (segments before t_seg are skipped)
    for t_seg in transcript.segments:
        # Advance past diarization segments that end before this segment starts.
        while d_base < d_len and d_segs[d_base].end_sec <= t_seg.start_sec:
            d_base += 1
        # Scan candidates that can overlap with this transcript segment.
        speaker = ""
        best_overlap = 0.0
        j = d_base
        while j < d_len and d_segs[j].start_sec < t_seg.end_sec:
            overlap = min(t_seg.end_sec, d_segs[j].end_sec) - max(
                t_seg.start_sec, d_segs[j].start_sec
            )
            if overlap > best_overlap:
                best_overlap = overlap
                speaker = d_segs[j].speaker
            j += 1
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


def _default_analyze(transcript: str, /) -> LlmAnalysisResult | None:
    """Call Ollama; return None and warn if unreachable (graceful degradation)."""
    try:
        return analyze_transcript(transcript)
    except OllamaError:
        _logger.warning("Ollama unavailable; LLM analysis skipped")
        return None


def run_pipeline(  # noqa: PLR0913
    audio_path: Path,
    db_path: Path,
    *,
    recorded_at: str | None = None,
    transcribe_fn: _TranscribeFnProtocol | None = None,
    diarize_fn: _DiarizeFnProtocol | None = None,
    embed_fn: _EmbedFnProtocol | None = None,
    analyze_fn: _AnalyzeFnProtocol | None = None,
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
    transcribe_fn / diarize_fn / embed_fn / analyze_fn:
        Callable overrides for each pipeline stage (used in tests).
        Pass ``analyze_fn=lambda _: None`` to skip LLM analysis in tests.

    Returns
    -------
    PipelineResult
        Contains the ad_id, transcript, diarization, voice embeddings, and
        optional LLM analysis (``None`` when Ollama is unreachable).

    Raises
    ------
    RuntimeError
        Wraps any exception from the pipeline stages.  The ad status is set
        to ``'error'`` in the database before raising.  The original exception
        is preserved in ``__cause__`` (``raise RuntimeError(...) from exc``).
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
    _analyze: _AnalyzeFnProtocol = (
        analyze_fn if analyze_fn is not None else _default_analyze
    )

    filename = audio_path.name

    with db.connect(db_path) as conn:
        ad_id = db.insert_ad(conn, filename, recorded_at)
        db.update_ad_status(conn, ad_id, "processing")

    try:
        transcript = _transcribe(audio_path)
        diarization = _diarize(audio_path)
        embedding_result = _embed(audio_path)
        embedding_blob = embedding_to_blob(embedding_result.embedding)

        segments = _assign_speakers(transcript, diarization)
        llm_analysis = _analyze(transcript.full_text)

        with db.connect(db_path) as conn:
            db.upsert_transcript(
                conn,
                ad_id,
                transcript.full_text,
                transcript.language,
                transcript.whisper_model,
            )
            db.insert_segments(conn, ad_id, segments)
            # Store a single whole-audio embedding (speaker="" key).
            # The embedder operates on the full audio rather than per-speaker
            # segments, so storing one record avoids misleadingly duplicating
            # the same blob under each diarized speaker label.
            db.upsert_voice_embedding(conn, ad_id, "", embedding_blob)
            if llm_analysis is not None:
                db.upsert_llm_analysis(
                    conn,
                    ad_id,
                    raw_response=llm_analysis.raw_response,
                    product_name=llm_analysis.product_name,
                    ad_type=llm_analysis.ad_type,
                    summary=llm_analysis.summary,
                    tone=llm_analysis.tone,
                )
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
        embeddings={"": embedding_result},
        llm_analysis=llm_analysis,
    )
