from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest

from src import db
from src.diarizer import DiarizationResult, DiarizationSegment
from src.embedder import EmbeddingResult
from src.pipeline import PipelineResult, run_pipeline
from src.transcriber import TranscriptResult, TranscriptSegment

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_transcript(
    texts: list[str] | None = None,
    starts: list[float] | None = None,
    ends: list[float] | None = None,
    language: str = "ja",
    whisper_model: str = "tiny",
) -> TranscriptResult:
    if texts is None:
        texts = ["こんにちは", "世界"]
    if starts is None:
        starts = [0.0, 1.0]
    if ends is None:
        ends = [1.0, 2.0]
    segs = [
        TranscriptSegment(text=t, start_sec=s, end_sec=e)
        for t, s, e in zip(texts, starts, ends, strict=True)
    ]
    return TranscriptResult(
        segments=segs, language=language, whisper_model=whisper_model
    )


def _make_diarization(
    speakers: list[str] | None = None,
    starts: list[float] | None = None,
    ends: list[float] | None = None,
    model_name: str = "pyannote/speaker-diarization-3.1",
) -> DiarizationResult:
    if speakers is None:
        speakers = ["SPEAKER_00", "SPEAKER_01"]
    if starts is None:
        starts = [0.0, 1.0]
    if ends is None:
        ends = [1.0, 2.0]
    segs = [
        DiarizationSegment(speaker=s, start_sec=st, end_sec=en)
        for s, st, en in zip(speakers, starts, ends, strict=True)
    ]
    return DiarizationResult(segments=segs, model_name=model_name)


def _make_embedding(dim: int = 256) -> EmbeddingResult:
    return EmbeddingResult(embedding=np.zeros(dim, dtype=np.float32))


def _setup_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "ads.db"
    db.init_db(db_path)
    return db_path


def _setup_audio(tmp_path: Path, name: str = "spotify_ad_test.wav") -> Path:
    audio = tmp_path / name
    audio.touch()
    return audio


# ---------------------------------------------------------------------------
# PipelineResult tests
# ---------------------------------------------------------------------------


def test_pipeline_result_repr() -> None:
    transcript = _make_transcript()
    diarization = _make_diarization()
    result = PipelineResult(
        ad_id=1,
        transcript=transcript,
        diarization=diarization,
        embeddings={"SPEAKER_00": _make_embedding(), "SPEAKER_01": _make_embedding()},
    )
    r = repr(result)
    assert "ad_id=1" in r
    assert "SPEAKER_00" in r


def test_pipeline_result_stores_all_fields() -> None:
    transcript = _make_transcript()
    diarization = _make_diarization()
    emb = _make_embedding()
    result = PipelineResult(
        ad_id=42,
        transcript=transcript,
        diarization=diarization,
        embeddings={"SPEAKER_00": emb},
    )
    assert result.ad_id == 42
    assert result.transcript is transcript
    assert result.diarization is diarization
    assert result.embeddings["SPEAKER_00"] is emb


# ---------------------------------------------------------------------------
# run_pipeline — happy path
# ---------------------------------------------------------------------------


def test_run_pipeline_returns_pipeline_result(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    audio = _setup_audio(tmp_path)
    transcript = _make_transcript()
    diarization = _make_diarization()
    embedding = _make_embedding()

    result = run_pipeline(
        audio,
        db_path,
        recorded_at="2026-01-01T00:00:00Z",
        transcribe_fn=lambda _: transcript,
        diarize_fn=lambda _: diarization,
        embed_fn=lambda _: embedding,
    )

    assert isinstance(result, PipelineResult)
    assert result.ad_id == 1
    assert result.transcript is transcript
    assert result.diarization is diarization


def test_run_pipeline_persists_ad_as_done(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    audio = _setup_audio(tmp_path)

    _ = run_pipeline(
        audio,
        db_path,
        recorded_at="2026-01-01T00:00:00Z",
        transcribe_fn=lambda _: _make_transcript(),
        diarize_fn=lambda _: _make_diarization(),
        embed_fn=lambda _: _make_embedding(),
    )

    with db.connect(db_path) as conn:
        ad = db.get_ad_by_filename(conn, audio.name)

    assert ad is not None
    assert ad["status"] == "done"
    assert ad["error_message"] is None


def test_run_pipeline_persists_transcript(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    audio = _setup_audio(tmp_path)
    transcript = _make_transcript(texts=["hello", "world"], language="en")

    result = run_pipeline(
        audio,
        db_path,
        recorded_at="2026-01-01T00:00:00Z",
        transcribe_fn=lambda _: transcript,
        diarize_fn=lambda _: _make_diarization(),
        embed_fn=lambda _: _make_embedding(),
    )

    with db.connect(db_path) as conn:
        row = db.get_transcript(conn, result.ad_id)

    assert row is not None
    assert row["language"] == "en"
    assert "hello" in row["full_text"]


def test_run_pipeline_persists_segments_with_speakers(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    audio = _setup_audio(tmp_path)
    # segment 0-1s → SPEAKER_00, segment 1-2s → SPEAKER_01
    transcript = _make_transcript(texts=["A", "B"], starts=[0.0, 1.0], ends=[1.0, 2.0])
    diarization = _make_diarization(
        speakers=["SPEAKER_00", "SPEAKER_01"],
        starts=[0.0, 1.0],
        ends=[1.0, 2.0],
    )

    result = run_pipeline(
        audio,
        db_path,
        recorded_at="2026-01-01T00:00:00Z",
        transcribe_fn=lambda _: transcript,
        diarize_fn=lambda _: diarization,
        embed_fn=lambda _: _make_embedding(),
    )

    with db.connect(db_path) as conn:
        segments = db.get_segments(conn, result.ad_id)

    assert len(segments) == 2
    assert segments[0]["speaker"] == "SPEAKER_00"
    assert segments[0]["text"] == "A"
    assert segments[1]["speaker"] == "SPEAKER_01"
    assert segments[1]["text"] == "B"


def test_run_pipeline_persists_voice_embeddings_per_speaker(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    audio = _setup_audio(tmp_path)
    diarization = _make_diarization(speakers=["SPEAKER_00", "SPEAKER_01"])

    result = run_pipeline(
        audio,
        db_path,
        recorded_at="2026-01-01T00:00:00Z",
        transcribe_fn=lambda _: _make_transcript(),
        diarize_fn=lambda _: diarization,
        embed_fn=lambda _: _make_embedding(),
    )

    with db.connect(db_path) as conn:
        embeddings = db.get_voice_embeddings(conn, result.ad_id)

    speakers_stored = {e["speaker"] for e in embeddings}
    assert speakers_stored == {"SPEAKER_00", "SPEAKER_01"}
    assert result.embeddings.keys() == {"SPEAKER_00", "SPEAKER_01"}


def test_run_pipeline_explicit_recorded_at(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    audio = _setup_audio(tmp_path)

    _ = run_pipeline(
        audio,
        db_path,
        recorded_at="2026-06-01T12:00:00Z",
        transcribe_fn=lambda _: _make_transcript(),
        diarize_fn=lambda _: _make_diarization(),
        embed_fn=lambda _: _make_embedding(),
    )

    with db.connect(db_path) as conn:
        ad = db.get_ad_by_filename(conn, audio.name)

    assert ad is not None
    assert ad["recorded_at"] == "2026-06-01T12:00:00Z"


def test_run_pipeline_default_recorded_at_from_stat(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    audio = _setup_audio(tmp_path)

    _ = run_pipeline(
        audio,
        db_path,
        transcribe_fn=lambda _: _make_transcript(),
        diarize_fn=lambda _: _make_diarization(),
        embed_fn=lambda _: _make_embedding(),
    )

    with db.connect(db_path) as conn:
        ad = db.get_ad_by_filename(conn, audio.name)

    assert ad is not None
    # Verify ISO-8601 UTC format: YYYY-MM-DDTHH:MM:SSZ
    assert len(ad["recorded_at"]) == 20
    assert ad["recorded_at"].endswith("Z")


def test_run_pipeline_empty_diarization_uses_empty_speaker(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    audio = _setup_audio(tmp_path)
    empty_diarization = DiarizationResult(
        segments=[], model_name="pyannote/speaker-diarization-3.1"
    )

    result = run_pipeline(
        audio,
        db_path,
        recorded_at="2026-01-01T00:00:00Z",
        transcribe_fn=lambda _: _make_transcript(),
        diarize_fn=lambda _: empty_diarization,
        embed_fn=lambda _: _make_embedding(),
    )

    with db.connect(db_path) as conn:
        embeddings = db.get_voice_embeddings(conn, result.ad_id)

    assert len(embeddings) == 1
    assert embeddings[0]["speaker"] == ""


def test_run_pipeline_empty_transcript_no_segments(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    audio = _setup_audio(tmp_path)
    empty_transcript = TranscriptResult(
        segments=[], language="ja", whisper_model="tiny"
    )

    result = run_pipeline(
        audio,
        db_path,
        recorded_at="2026-01-01T00:00:00Z",
        transcribe_fn=lambda _: empty_transcript,
        diarize_fn=lambda _: _make_diarization(),
        embed_fn=lambda _: _make_embedding(),
    )

    with db.connect(db_path) as conn:
        segments = db.get_segments(conn, result.ad_id)

    assert segments == []


# ---------------------------------------------------------------------------
# run_pipeline — error handling
# ---------------------------------------------------------------------------


def test_run_pipeline_sets_error_status_on_failure(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    audio = _setup_audio(tmp_path)

    def _bad_transcribe(_: Path) -> TranscriptResult:
        msg = "model load failed"
        raise OSError(msg)

    with pytest.raises(RuntimeError):
        _ = run_pipeline(
            audio,
            db_path,
            recorded_at="2026-01-01T00:00:00Z",
            transcribe_fn=_bad_transcribe,
            diarize_fn=lambda _: _make_diarization(),
            embed_fn=lambda _: _make_embedding(),
        )

    with db.connect(db_path) as conn:
        ad = db.get_ad_by_filename(conn, audio.name)

    assert ad is not None
    assert ad["status"] == "error"
    assert ad["error_message"] is not None
    assert "model load failed" in ad["error_message"]


def test_run_pipeline_reraises_as_runtime_error(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    audio = _setup_audio(tmp_path)

    def _bad_embed(_: Path) -> EmbeddingResult:
        msg = "embed failed"
        raise ValueError(msg)

    with pytest.raises(RuntimeError, match=audio.name):
        _ = run_pipeline(
            audio,
            db_path,
            recorded_at="2026-01-01T00:00:00Z",
            transcribe_fn=lambda _: _make_transcript(),
            diarize_fn=lambda _: _make_diarization(),
            embed_fn=_bad_embed,
        )


def test_run_pipeline_error_preserves_original_cause(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    audio = _setup_audio(tmp_path)

    def _bad_diarize(_: Path) -> DiarizationResult:
        msg = "hf token missing"
        raise RuntimeError(msg)

    with pytest.raises(RuntimeError) as exc_info:
        _ = run_pipeline(
            audio,
            db_path,
            recorded_at="2026-01-01T00:00:00Z",
            transcribe_fn=lambda _: _make_transcript(),
            diarize_fn=_bad_diarize,
            embed_fn=lambda _: _make_embedding(),
        )

    assert exc_info.value.__cause__ is not None
    assert "hf token missing" in str(exc_info.value.__cause__)
