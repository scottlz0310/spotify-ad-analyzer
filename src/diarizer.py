from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Protocol, TypedDict, cast, override

import numpy as np
from pyannote.audio import Pipeline

from src import config

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    import numpy.typing as npt
    import torch


class _SegmentProtocol(Protocol):
    """Minimal structural type for a pyannote time segment."""

    start: float
    end: float


class _AnnotationProtocol(Protocol):
    """Minimal structural type for a pyannote.core.Annotation object."""

    def itertracks(
        self, *, yield_label: bool = False
    ) -> Iterable[tuple[_SegmentProtocol, str, str]]: ...


class _DiarizeOutputProtocol(Protocol):
    """Minimal structural type for the DiarizeOutput returned by pyannote.audio 4.x."""

    speaker_diarization: _AnnotationProtocol


class _AudioInput(TypedDict):
    """Audio input accepted by pyannote Pipeline instead of a file path."""

    waveform: torch.Tensor  # TYPE_CHECKING-only; PEP 563 makes this a string at runtime
    sample_rate: int


class _SfReadFn(Protocol):
    """Typed callable for soundfile.read (float32, always_2d)."""

    def __call__(
        self, file: str, *, dtype: str, always_2d: bool
    ) -> tuple[npt.NDArray[np.float32], int]: ...


class _TorchFromNumpyFn(Protocol):
    """Typed callable for torch.from_numpy."""

    def __call__(self, ndarray: npt.NDArray[np.float32]) -> torch.Tensor: ...


class _PipelineProtocol(Protocol):
    """Minimal structural type for the pyannote Pipeline callable."""

    def __call__(self, file: _AudioInput) -> _DiarizeOutputProtocol: ...


class DiarizationSegment:
    """A single speaker turn from a diarization result."""

    __slots__: tuple[str, ...] = ("end_sec", "speaker", "start_sec")
    speaker: str
    start_sec: float
    end_sec: float

    def __init__(self, *, speaker: str, start_sec: float, end_sec: float) -> None:
        self.speaker = speaker
        self.start_sec = start_sec
        self.end_sec = end_sec

    @override
    def __repr__(self) -> str:
        return (
            f"DiarizationSegment(speaker={self.speaker!r}, "
            f"start_sec={self.start_sec}, end_sec={self.end_sec})"
        )


class DiarizationResult:
    """Full diarization result for one audio file."""

    __slots__: tuple[str, ...] = ("model_name", "segments")
    segments: list[DiarizationSegment]
    model_name: str

    def __init__(self, *, segments: list[DiarizationSegment], model_name: str) -> None:
        self.segments = segments
        self.model_name = model_name

    @property
    def speakers(self) -> list[str]:
        """Sorted list of unique speaker labels."""
        return sorted({s.speaker for s in self.segments})


class _PipelineFactoryProtocol(Protocol):
    """Minimal structural type for ``Pipeline.from_pretrained``."""

    @classmethod
    def from_pretrained(
        cls,
        checkpoint: str,
        *,
        token: str | None = None,
    ) -> _PipelineProtocol | None: ...


def _load_audio(audio_path: Path) -> _AudioInput:
    """Load audio with soundfile, bypassing the torchcodec/FFmpeg decoder.

    pyannote-audio 4.x uses torchcodec internally, whose FFmpeg backend
    rejects certain PCM WAV files with ``Invalid data found when processing
    input``.  Passing a pre-loaded waveform tensor dict bypasses that
    decoder entirely.
    """
    sf_mod = importlib.import_module("soundfile")
    sf_read = cast("_SfReadFn", sf_mod.read)
    data, sr = sf_read(str(audio_path), dtype="float32", always_2d=True)
    # soundfile: (n_samples, n_channels) → pyannote expects (n_channels, n_samples)
    contiguous: npt.NDArray[np.float32] = np.ascontiguousarray(data.T)
    torch_mod = importlib.import_module("torch")
    from_numpy = cast("_TorchFromNumpyFn", torch_mod.from_numpy)
    waveform = from_numpy(contiguous)
    return _AudioInput(waveform=waveform, sample_rate=int(sr))


def _load_pipeline(model_name: str, hf_token: str) -> _PipelineProtocol:
    """Load a pyannote.audio pipeline from the HuggingFace Hub."""
    factory = cast("_PipelineFactoryProtocol", Pipeline)
    result = factory.from_pretrained(model_name, token=hf_token or None)
    if result is None:
        msg = f"Pipeline.from_pretrained returned None for model {model_name!r}"
        raise RuntimeError(msg)
    return result


def diarize(
    audio_path: Path,
    *,
    pipeline: _PipelineProtocol | None = None,
    model_name: str | None = None,
) -> DiarizationResult:
    """Diarize *audio_path* and return a :class:`DiarizationResult`.

    Parameters
    ----------
    audio_path:
        Path to the WAV (or any audio) file to diarize.
    pipeline:
        Pre-loaded pipeline callable.  When *None* (default), a new pipeline
        is loaded using *model_name* and :data:`src.config.HF_TOKEN`.
    model_name:
        HuggingFace model identifier.  Defaults to
        :data:`src.config.DIARIZE_MODEL` when *None*.
    """
    if model_name is None:
        model_name = config.DIARIZE_MODEL
    if pipeline is None:
        pipeline = _load_pipeline(model_name, config.HF_TOKEN)

    output = pipeline(_load_audio(audio_path))

    segments: list[DiarizationSegment] = [
        DiarizationSegment(
            speaker=label,
            start_sec=turn.start,
            end_sec=turn.end,
        )
        for turn, _, label in output.speaker_diarization.itertracks(yield_label=True)
    ]

    return DiarizationResult(segments=segments, model_name=model_name)
